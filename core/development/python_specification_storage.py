"""Bounded storage policy with explicit, nonblocking function-decorator assurance limits."""
from __future__ import annotations

import ast

from core.development.python_specification_dependencies import dynamic_reference, import_roots

STORAGE_MODULES = frozenset({"sqlite3", "dbm", "shelve", "pickle", "pathlib", "tempfile", "io", "os", "shutil"})
STORAGE_CALLS = frozenset({"open"})
DECORATOR_ASSURANCE = "Storage requirement passed by bounded static inspection; decorator effects were not statically verified."

PURE_CONSTRUCTORS = frozenset({"dict", "list", "tuple", "set", "frozenset", "str", "int", "float", "bool", "len", "range"})


def storage_findings(trees: tuple[ast.Module, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    violations: list[str] = []
    unknown: list[str] = []
    for tree in trees:
        shadowed = bound_names(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Subscript, ast.BinOp, ast.UnaryOp, ast.Compare, ast.For,
                                 ast.With, ast.Await, ast.Yield, ast.comprehension)):
                unknown.append("opaque protocol/operator effects")
            if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "self"):
                unknown.append("opaque attribute/property effects")
            roots = import_roots(node)
            if set(roots) & STORAGE_MODULES:
                violations.append(f"line {getattr(node, "lineno", 0)}: storage/filesystem module reference")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                unknown.append(f"line {getattr(node, "lineno", 0)}: imported runtime effects are not established")
            if dynamic_reference(node):
                unknown.append(f"line {getattr(node, "lineno", 0)}: dynamic runtime effects")
            if isinstance(node, ast.Call):
                name = call_name(node)
                if isinstance(node.func, ast.Name) and name in STORAGE_CALLS and name not in shadowed:
                    violations.append(f"line {getattr(node, "lineno", 0)}: storage API reference {name}")
                elif not isinstance(node.func, ast.Name) or name not in PURE_CONSTRUCTORS or name in shadowed or node.keywords or any(not isinstance(arg, ast.Constant) for arg in node.args):
                    unknown.append(f"line {getattr(node, "lineno", 0)}: opaque call effects {name}")
            if isinstance(node, ast.ClassDef) and (node.bases or node.decorator_list or node.keywords):
                unknown.append(f"line {getattr(node, "lineno", 0)}: opaque class effects")
    return tuple(violations), tuple(unknown)


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    return node.func.attr if isinstance(node.func, ast.Attribute) else "<dynamic>"


def bound_names(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
    return names


def decorator_warnings(trees: tuple[ast.Module, ...], paths: tuple[str, ...]) -> tuple[str, ...]:
    """Report every function decorator without claiming its semantics are verified.

    The normal storage walk still visits decorator expressions and function bodies:
    positive storage references and other blocking unknowns are never suppressed.
    Class decorators remain under the existing opaque-class policy.
    """
    occurrences = sorted(
        (path, decorator.lineno, decorator.col_offset, node.name, ast.unparse(decorator))
        for tree, path in zip(trees, paths)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        for decorator in node.decorator_list
    )
    return tuple(
        f"assurance_warning: {path}:{line}: @{identity} on {name}; "
        "decorator effects were not statically verified"
        for path, line, _column, name, identity in occurrences
    )
