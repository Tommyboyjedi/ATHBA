"""Syntactic parameter binding edits; no inference about function behavior."""
from __future__ import annotations
import ast
import io
import tokenize
from dataclasses import dataclass, replace
from core.development.post_behavior_rename import (
    DeclarationKind, PythonRenameReferences, RenameTarget, module_name, token_within,
)
from core.development.specification_evidence_policy import RevisionFile

UNSAFE_NAMES = frozenset({"locals", "globals", "vars", "eval", "exec", "getattr", "setattr", "delattr", "__import__"})
NESTED_BINDINGS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda,
                  ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
                  ast.Global, ast.Nonlocal, ast.Import, ast.ImportFrom, ast.Match, ast.ExceptHandler)

@dataclass(frozen=True)
class ParameterTokenSearch:
    tokens: tuple[tokenize.TokenInfo, ...]
    file: RevisionFile

    def positions(self, node: ast.AST, name: str) -> frozenset[tuple[int, int]]:
        matches = [token.start for token in self.tokens if token.type == tokenize.NAME
                   and token.string == name and token_within(token, node, self.file.source)]
        return frozenset(matches[:1])

@dataclass(frozen=True)
class PythonParameterReferences:
    target: RenameTarget
    file: RevisionFile

    def positions(self) -> frozenset[tuple[int, int]]:
        tree = ast.parse(self.file.source)
        if any(isinstance(node, ast.Name) and node.id in UNSAFE_NAMES
               or isinstance(node, ast.Attribute) and node.attr.startswith("__") for node in ast.walk(tree)):
            raise ValueError("dynamic parameter references cannot be proven")
        tokens = tuple(tokenize.generate_tokens(io.StringIO(self.file.source).readline))
        search = ParameterTokenSearch(tokens, self.file)
        result: set[tuple[int, int]] = set()
        if self.file.path == self.target.path:
            function = _function(tree, self.target)
            arguments = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
            if function.decorator_list or function.args.vararg or function.args.kwarg or function.args.defaults:
                raise ValueError("unsupported parameter declaration")
            bodies = tuple(node for statement in function.body for node in ast.walk(statement))
            if any(isinstance(node, NESTED_BINDINGS) for node in bodies):
                raise ValueError("nested or indirect parameter binding unsupported")
            if any(arg.arg == self.target.replacement for arg in arguments) or any(
                    isinstance(node, ast.Name) and node.id == self.target.replacement for node in bodies):
                raise ValueError("parameter rename would capture an existing binding")
            parameter = next((arg for arg in arguments if arg.arg == self.target.name), None)
            if parameter is None:
                raise ValueError("parameter declaration absent")
            result.update(search.positions(parameter, self.target.name))
            for node in bodies:
                if isinstance(node, ast.Name) and node.id == self.target.name:
                    result.update(search.positions(node, self.target.name))
        operation = replace(self.target, name=self.target.operation, operation="", kind=DeclarationKind.SYMBOL)
        references = PythonRenameReferences(operation, self.file).positions()
        calls = {id(node.func): node for node in ast.walk(tree) if isinstance(node, ast.Call)}
        for node in ast.walk(tree):
            name = node.attr if isinstance(node, ast.Attribute) else node.id if isinstance(node, ast.Name) else None
            if name != operation.name:
                continue
            bound = bool(search.positions(node, operation.name) & references)
            call = calls.get(id(node))
            if bound and call is None:
                raise ValueError("escaping callable parameter references unsupported")
            if call is None:
                continue
            relevant = any(keyword.arg in {None, self.target.name} for keyword in call.keywords)
            if relevant and not bound:
                raise ValueError("keyword call receiver is not mechanically resolved")
            if bound:
                if any(keyword.arg is None for keyword in call.keywords):
                    raise ValueError("dynamic keyword arguments unsupported")
                for keyword in call.keywords:
                    if keyword.arg == self.target.name:
                        result.update(search.positions(keyword, self.target.name))
        return frozenset(result)

def _function(tree: ast.Module, target: RenameTarget) -> ast.FunctionDef:
    body = tree.body
    if target.owner:
        owners = [node for node in body if isinstance(node, ast.ClassDef) and node.name == target.owner]
        if len(owners) != 1 or owners[0].bases or owners[0].keywords or owners[0].decorator_list:
            raise ValueError("parameter owner is not a plain owned declaration")
        body = owners[0].body
    functions = [node for node in body if isinstance(node, ast.FunctionDef)
                 and node.name == target.operation and node.lineno == target.declaration_line]
    if len(functions) != 1:
        raise ValueError("parameter target is not one ordinary function")
    return functions[0]
