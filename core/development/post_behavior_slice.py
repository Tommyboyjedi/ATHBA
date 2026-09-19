"""Focused Python production context reconstructed from immutable accepted revisions."""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath

from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.development.specification_revision_snapshot import production_python

PYTHON_SOURCE_SUFFIX = ".py"
UNSUPPORTED_SOURCE_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx", ".java", ".rs", ".go", ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".swift", ".kt"})


@dataclass(frozen=True)
class ProductionSliceScope:
    entry_revision: str
    behaviorally_accepted_revision: str
    production_paths: tuple[str, ...]


@dataclass(frozen=True)
class SourceRegion:
    path: str
    start_line: int
    end_line: int
    identity: tuple[str, ...]


@dataclass(frozen=True)
class FocusedProductionSlice:
    revision: str
    files: tuple[RevisionFile, ...]
    scope: ProductionSliceScope
    regions: tuple[SourceRegion, ...] = ()

    @property
    def identity(self) -> str:
        material = repr((self.revision, self.scope, self.files, self.regions))
        return hashlib.sha256(material.encode()).hexdigest()


@dataclass(frozen=True)
class SliceRequest:
    entry: SpecificationSnapshot
    accepted: SpecificationSnapshot
    scope: ProductionSliceScope | None = None


@dataclass(frozen=True)
class PythonSourceUnit:
    identity: tuple[str, ...]
    node: ast.stmt
    headers: tuple[ast.ClassDef, ...] = ()


class PythonProductionSlice:
    """Select changed syntax units, retaining only their required import/header context."""

    def derive(self, request: SliceRequest) -> FocusedProductionSlice:
        entry, accepted = request.entry, request.accepted
        if not entry.complete or not accepted.complete:
            raise ValueError("focused production requires complete immutable snapshots")
        if request.scope and request.scope.entry_revision != entry.revision:
            raise ValueError("focused production entry revision mismatch")
        before = {file.path: file for file in entry.files}
        if any(before.get(file.path) != file and unsupported_production(file) for file in accepted.files):
            raise ValueError("unsupported production language")
        paths = tuple(sorted(file.path for file in accepted.files
                             if production_python(file) and before.get(file.path) != file))
        scope = request.scope or ProductionSliceScope(entry.revision, accepted.revision, paths)
        sources: list[RevisionFile] = []
        regions: list[SourceRegion] = []
        for file in accepted.files:
            if file.path not in scope.production_paths:
                continue
            if not production_python(file):
                raise ValueError("unsupported production language")
            previous = before.get(file.path, RevisionFile(file.path, ""))
            units = changed_units(previous.source, file.source)
            selected = focused_source(file.source, units)
            if selected:
                sources.append(RevisionFile(file.path, selected))
            regions.extend(SourceRegion(file.path, start_line(unit.node), end_line(unit.node),
                                        unit.identity) for unit in units)
        if set(scope.production_paths) - {file.path for file in accepted.files}:
            raise ValueError("accepted production path disappeared")
        return FocusedProductionSlice(accepted.revision, tuple(sources), scope, tuple(regions))


def start_line(node: ast.AST) -> int:
    decorators = getattr(node, "decorator_list", ())
    return min([getattr(node, "lineno", 1)] + [item.lineno for item in decorators])


def end_line(node: ast.AST) -> int:
    value = getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)
    return value if isinstance(value, int) else 1


def node_source(source: str, node: ast.AST) -> str:
    return "".join(source.splitlines(keepends=True)[start_line(node) - 1:end_line(node)])


def node_key(node: ast.stmt, ordinal: int) -> str:
    return f"{type(node).__name__}:{getattr(node, 'name', ordinal)}"


def class_header(node: ast.ClassDef) -> str:
    fields = (node.name, tuple(ast.dump(item) for item in node.bases),
              tuple(ast.dump(item) for item in node.keywords),
              tuple(ast.dump(item) for item in node.decorator_list),
              tuple(ast.dump(item) for item in getattr(node, "type_params", ())))
    return repr(fields)


def changed_units(previous: str, current: str) -> tuple[PythonSourceUnit, ...]:
    before, after = ast.parse(previous), ast.parse(current)
    return _changed_body((before.body, after.body), (previous, current, (), ()))


def _changed_body(bodies: tuple[list[ast.stmt], list[ast.stmt]],
                  context: tuple[str, str, tuple[str, ...], tuple[ast.ClassDef, ...]]) -> tuple[PythonSourceUnit, ...]:
    previous, current, prefix, headers = context
    old = {node_key(node, index): node for index, node in enumerate(bodies[0])}
    result: list[PythonSourceUnit] = []
    for index, node in enumerate(bodies[1]):
        key = node_key(node, index)
        prior = old.get(key)
        if prior is not None and node_source(previous, prior) == node_source(current, node):
            continue
        identity = (*prefix, key)
        if isinstance(node, ast.ClassDef) and isinstance(prior, ast.ClassDef) and class_header(node) == class_header(prior):
            result.extend(_changed_body((prior.body, node.body),
                                        (previous, current, identity, (*headers, node))))
        else:
            result.append(PythonSourceUnit(identity, node, headers))
    return tuple(result)


def focused_source(source: str, units: tuple[PythonSourceUnit, ...]) -> str:
    lines = source.splitlines(keepends=True)
    chosen: set[int] = set()
    used = {node.id for unit in units for node in ast.walk(unit.node) if isinstance(node, ast.Name)}
    for unit in units:
        chosen.update(range(start_line(unit.node) - 1, end_line(unit.node)))
        for header in unit.headers:
            if header.body[0].lineno == header.lineno:
                raise ValueError("inline class bodies are not safely sliceable")
            chosen.update(range(start_line(header) - 1, start_line(header.body[0]) - 1))
            for expression in (*header.bases, *header.decorator_list, *header.keywords):
                used.update(node.id for node in ast.walk(expression) if isinstance(node, ast.Name))
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            bindings = {alias.asname or alias.name.split(".")[0] for alias in node.names}
            if used & bindings or isinstance(node, ast.ImportFrom) and node.module == "__future__":
                chosen.update(range(start_line(node) - 1, end_line(node)))
    return "".join(line for index, line in enumerate(lines) if index in chosen)


def unsupported_production(file: RevisionFile) -> bool:
    path = PurePosixPath(file.path)
    return path.suffix in UNSUPPORTED_SOURCE_SUFFIXES and not (
        set(path.parts) & {"tests", "test"} or path.name.startswith("test_")
    )
