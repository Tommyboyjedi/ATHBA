"""Conservative static Python binding resolution for one exact identifier rename."""
from __future__ import annotations

import ast
import io
import tokenize
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from core.development.post_behavior_slice import FocusedProductionSlice, end_line, start_line
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.development.specification_revision_snapshot import production_python


class DeclarationKind(str, Enum):
    SYMBOL = "symbol"
    FIELD = "field"


class BindingKind(str, Enum):
    SYMBOL = "symbol"
    OWNER = "owner"
    MODULE = "module"
    INSTANCE = "instance"


@dataclass(frozen=True)
class RenameTarget:
    path: str
    module: str
    owner: str
    name: str
    replacement: str
    declaration_line: int
    kind: DeclarationKind = DeclarationKind.SYMBOL


@dataclass(frozen=True)
class RenameSelection:
    snapshot: SpecificationSnapshot
    production: FocusedProductionSlice
    current_name: str
    required_name: str


@dataclass(frozen=True)
class FocusedRenameSelection:
    files: tuple[RevisionFile, ...]
    current_name: str
    required_name: str


@dataclass(frozen=True)
class ReferenceScope:
    bindings: tuple[tuple[str, BindingKind], ...]
    owner: str = ""
    depth: int = 0

    def binding(self, name: str) -> BindingKind | None:
        return next((kind for key, kind in self.bindings if key == name), None)


def module_name(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


@dataclass(frozen=True)
class PythonDeclaration:
    owner: str
    name: str
    node: ast.AST
    kind: DeclarationKind = DeclarationKind.SYMBOL


def select_target(request: RenameSelection) -> RenameTarget:
    matches: list[RenameTarget] = []
    for file in request.snapshot.files:
        if not production_python(file):
            continue
        available = declarations(ast.parse(file.source).body)
        for declaration in available:
            if declaration.name != request.current_name:
                continue
            if any(region.path == file.path and region.start_line <= start_line(declaration.node) <= region.end_line
                   for region in request.production.regions):
                target = _declaration_target(file, (declaration, request.required_name))
                _require_available_name(target, available)
                matches.append(target)
    return _unique_target(matches)


def select_focused_target(request: FocusedRenameSelection) -> RenameTarget:
    matches: list[RenameTarget] = []
    for file in request.files:
        if not production_python(file):
            raise ValueError("focused rename target must be production Python")
        available = declarations(ast.parse(file.source).body)
        for declaration in available:
            if declaration.name == request.current_name:
                target = _declaration_target(file, (declaration, request.required_name))
                _require_available_name(target, available)
                matches.append(target)
    return _unique_target(matches)


def _declaration_target(file: RevisionFile, selection: tuple[PythonDeclaration, str]) -> RenameTarget:
    declaration, required_name = selection
    node = declaration.node
    return RenameTarget(file.path, module_name(file.path), declaration.owner, declaration.name,
                        required_name, getattr(node, "lineno", start_line(node)), declaration.kind)


def _require_available_name(target: RenameTarget, available: tuple[PythonDeclaration, ...]) -> None:
    if any(item.owner == target.owner and item.name == target.replacement for item in available):
        raise ValueError("required identifier already exists in the target scope")


def _unique_target(matches: list[RenameTarget]) -> RenameTarget:
    unique: list[RenameTarget] = []
    for target in matches:
        if target.kind == DeclarationKind.FIELD and any(
            item.path == target.path and item.owner == target.owner and item.name == target.name
            and item.kind == DeclarationKind.FIELD for item in unique
        ):
            continue
        unique.append(target)
    if len(unique) != 1:
        raise ValueError("rename target must resolve to one focused declaration")
    return unique[0]


def declarations(body: list[ast.stmt], owner: str = "") -> tuple[PythonDeclaration, ...]:
    result: list[PythonDeclaration] = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result.append(PythonDeclaration(owner, node.name, node))
        if isinstance(node, ast.ClassDef) and not owner:
            result.extend(declarations(node.body, node.name))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            result.extend(PythonDeclaration(owner, target.id, target, DeclarationKind.FIELD)
                          for target in targets if isinstance(target, ast.Name))
        elif owner and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = (*node.args.posonlyargs, *node.args.args)
            if arguments and arguments[0].arg in {"self", "cls"}:
                result.extend(PythonDeclaration(owner, item.attr, item, DeclarationKind.FIELD)
                              for item in scoped_nodes(node.body) if isinstance(item, ast.Attribute)
                              and isinstance(item.ctx, ast.Store) and isinstance(item.value, ast.Name)
                              and item.value.id == arguments[0].arg)
    return tuple(result)


def declared_identifier_names(files: tuple[RevisionFile, ...]) -> tuple[str, ...]:
    return tuple(sorted({item.name for file in files for item in declarations(ast.parse(file.source).body)}))


def scoped_nodes(body: list[ast.stmt]) -> tuple[ast.AST, ...]:
    result: list[ast.AST] = []
    pending: list[ast.AST] = list(reversed(body))
    while pending:
        node = pending.pop()
        result.append(node)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))
    return tuple(result)


@dataclass
class PythonRenameReferences:
    target: RenameTarget
    file: RevisionFile

    def positions(self) -> frozenset[tuple[int, int]]:
        self.tokens = tuple(tokenize.generate_tokens(io.StringIO(self.file.source).readline))
        self.found: set[tuple[int, int]] = set()
        tree = ast.parse(self.file.source)
        bindings = self._imports(scoped_nodes(tree.body))
        if module_name(self.file.path) == self.target.module:
            bindings[self.target.owner or self.target.name] = BindingKind.OWNER if self.target.owner else BindingKind.SYMBOL
        self._walk(tree.body, ReferenceScope(tuple(bindings.items())))
        return frozenset(self.found)

    def _imports(self, nodes: tuple[ast.AST, ...]) -> dict[str, BindingKind]:
        bindings: dict[str, BindingKind] = {}
        for node in nodes:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bindings.pop(alias.asname or alias.name.split(".")[0], None)
            if isinstance(node, ast.ImportFrom) and not node.level and node.module == self.target.module:
                for alias in node.names:
                    if alias.name == (self.target.owner or self.target.name):
                        bindings[alias.asname or alias.name] = BindingKind.OWNER if self.target.owner else BindingKind.SYMBOL
                        if not self.target.owner:
                            self._mark(alias)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == self.target.module and (alias.asname or "." not in alias.name):
                        bindings[alias.asname or alias.name] = BindingKind.MODULE
        return bindings

    def _walk(self, body: list[ast.stmt], scope: ReferenceScope) -> None:
        nodes = scoped_nodes(body)
        scope = inferred_scope(nodes, scope)
        bindings = dict(scope.bindings)
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                own_target = self.file.path == self.target.path and (
                    getattr(node, "lineno", 0) == self.target.declaration_line or
                    isinstance(node, ast.ClassDef) and node.name == self.target.owner)
                if not own_target:
                    bindings.pop(node.name, None)
        if self.target.kind == DeclarationKind.FIELD and self.file.path == self.target.path and scope.depth == 0:
            if scope.owner == self.target.owner:
                bindings[self.target.name] = BindingKind.SYMBOL
        scope = ReferenceScope(tuple(bindings.items()), scope.owner, scope.depth)
        for node in nodes:
            if isinstance(node, ast.Name):
                if node.id == self.target.name and scope.binding(node.id) == BindingKind.SYMBOL:
                    self._mark(node)
            elif isinstance(node, ast.Attribute) and node.attr == self.target.name:
                kind = expression_binding(node.value, scope, self.target)
                allowed = {BindingKind.OWNER, BindingKind.INSTANCE} if self.target.owner else {BindingKind.MODULE}
                if kind in allowed:
                    self._mark(node, last=True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._function(node, scope)
            elif isinstance(node, ast.ClassDef):
                own_file = module_name(self.file.path) == self.target.module
                if own_file and node.lineno == self.target.declaration_line and not self.target.owner and node.name == self.target.name:
                    self._definition(node)
                nested = ReferenceScope(scope.bindings, node.name if own_file else "", scope.depth)
                self._walk(node.body, nested)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, scope: ReferenceScope) -> None:
        own_file = module_name(self.file.path) == self.target.module
        if own_file and node.lineno == self.target.declaration_line and scope.owner == self.target.owner and node.name == self.target.name:
            self._definition(node)
        bindings = dict(scope.bindings)
        if self.target.owner and scope.depth == 0:
            bindings.pop(self.target.name, None)
        local_nodes = scoped_nodes(node.body)
        shadowed = {item.id for item in local_nodes if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)}
        arguments = (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
        shadowed.update(item.arg for item in arguments)
        shadowed.update(alias.asname or alias.name.split(".")[0] for item in local_nodes
                        if isinstance(item, (ast.Import, ast.ImportFrom)) for alias in item.names)
        shadowed.update(item.arg for item in (node.args.vararg, node.args.kwarg) if item)
        for name in shadowed:
            bindings.pop(name, None)
        bindings.update(self._imports(local_nodes))
        if scope.owner == self.target.owner and self.target.owner and arguments and arguments[0].arg in {"self", "cls"}:
            bindings[arguments[0].arg] = BindingKind.INSTANCE
        self._walk(node.body, ReferenceScope(tuple(bindings.items()), scope.owner, scope.depth + 1))

    def _definition(self, node: ast.AST) -> None:
        candidates = [item for item in self.tokens if item.type == tokenize.NAME and item.string == self.target.name
                      and getattr(node, "lineno", 1) <= item.start[0] <= end_line(node)]
        if not candidates:
            raise ValueError("rename declaration token unavailable")
        self.found.add(candidates[0].start)

    def _mark(self, node: ast.AST, last: bool = False) -> None:
        candidates = [item for item in self.tokens if item.type == tokenize.NAME and item.string == self.target.name
                      and token_within(item, node, self.file.source)]
        if not candidates:
            raise ValueError("rename reference token unavailable")
        self.found.add(candidates[-1 if last else 0].start)


def token_within(token: tokenize.TokenInfo, node: ast.AST, source: str) -> bool:
    lines = source.splitlines()
    start = (token.start[0], len(lines[token.start[0] - 1][:token.start[1]].encode()))
    finish = (end_line(node), getattr(node, "end_col_offset", 0))
    return (getattr(node, "lineno", 1), getattr(node, "col_offset", 0)) <= start <= finish and getattr(node, "lineno", 1) <= token.start[0] <= end_line(node)


def expression_binding(node: ast.AST, scope: ReferenceScope, target: RenameTarget) -> BindingKind | None:
    if isinstance(node, ast.Name):
        return scope.binding(node.id)
    if isinstance(node, ast.Attribute) and node.attr == target.owner:
        if expression_binding(node.value, scope, target) == BindingKind.MODULE:
            return BindingKind.OWNER
    if isinstance(node, ast.Call) and expression_binding(node.func, scope, target) == BindingKind.OWNER:
        return BindingKind.INSTANCE
    return None


def inferred_scope(nodes: tuple[ast.AST, ...], scope: ReferenceScope) -> ReferenceScope:
    bindings = dict(scope.bindings)
    assigned: dict[str, list[ast.AST | None]] = {}
    for node in nodes:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, []).append(node.value)
    for name, values in assigned.items():
        if len(values) != 1:
            bindings.pop(name, None)
        elif isinstance(values[0], ast.Call) and isinstance(values[0].func, ast.Name):
            if scope.binding(values[0].func.id) == BindingKind.OWNER:
                bindings[name] = BindingKind.INSTANCE
            else:
                bindings.pop(name, None)
        else:
            bindings.pop(name, None)
    return ReferenceScope(tuple(bindings.items()), scope.owner, scope.depth)


def exact_renamed_source(file: RevisionFile, target: RenameTarget) -> str:
    positions = PythonRenameReferences(target, file).positions()
    tokens = tokenize.generate_tokens(io.StringIO(file.source).readline)
    result = [item._replace(string=target.replacement) if item.start in positions else item for item in tokens]
    return tokenize.untokenize(result)
