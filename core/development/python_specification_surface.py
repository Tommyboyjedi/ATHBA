"""Conservative declared Python API inspection; no behavioral inference."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

CAPABILITY_TOKENS = {
    "deletion": frozenset({"delete", "deletion", "remove"}),
    "subscriptions": frozenset({"subscribe", "subscription", "subscriptions", "unsubscribe"}),
    "persistence": frozenset({"persist", "persistence", "save", "load"}),
    "concurrency": frozenset({"concurrent", "concurrency", "thread", "async"}),
    "validation rules": frozenset({"validate", "validation"}),
}
DYNAMIC_SURFACE = frozenset({"setattr", "delattr", "exec", "eval", "globals", "locals", "__getattr__", "__getattribute__"})


@dataclass(frozen=True)
class PythonPublicSurface:
    names: tuple[str, ...]
    complete: bool


def inspect_surface(trees: tuple[ast.Module, ...]) -> PythonPublicSurface:
    names: set[str] = set()
    complete = True
    for tree in trees:
        complete = complete and declared_body_complete(tree.body)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in DYNAMIC_SURFACE or node.decorator_list:
                    complete = False
                if isinstance(node, ast.ClassDef) and (node.bases or node.keywords):
                    complete = False
            if isinstance(node, ast.Name) and node.id in DYNAMIC_SURFACE:
                complete = False
            if isinstance(node, ast.Attribute) and node.attr in {"__dict__", "__class__", "__bases__"}:
                complete = False
        collect_declared_names(tree.body, names)
    return PythonPublicSurface(tuple(sorted(names)), complete)


def collect_declared_names(body: list[ast.stmt], names: set[str]) -> None:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                names.add(node.name)
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                collect_declared_names(node.body, names)
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        names.update(child.attr for child in ast.walk(method)
                                     if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store)
                                     and isinstance(child.value, ast.Name) and child.value.id == "self"
                                     and not child.attr.startswith("_"))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(target.id for target in targets if isinstance(target, ast.Name) and not target.id.startswith("_"))
        elif isinstance(node, ast.If):
            collect_declared_names(node.body + node.orelse, names)


def capability_matches(subject: str, names: tuple[str, ...]) -> tuple[str, ...]:
    tokens: set[str] = set()
    for phrase, aliases in CAPABILITY_TOKENS.items():
        if re.search(r'\b' + re.escape(phrase) + r'\b', subject) or subject in aliases:
            tokens.update(aliases)
    # Exact explicitly named identifiers are supported without guessing their meaning.
    tokens.update(re.findall(r'`([A-Za-z_]\w*)`', subject))
    return tuple(name for name in names if tokens.intersection(identifier_tokens(name)) or name.lower() in tokens)


def known_capability(subject: str) -> bool:
    return any(re.search(r'\b' + re.escape(phrase) + r'\b', subject) or subject in aliases
               for phrase, aliases in CAPABILITY_TOKENS.items()) or bool(re.search(r'`[A-Za-z_]\w*`', subject))


def identifier_tokens(name: str) -> set[str]:
    split = re.sub(r'([a-z])([A-Z])', r'\1_\2', name).lower()
    return set(split.split("_"))


def declared_body_complete(body: list[ast.stmt]) -> bool:
    for node in body:
        if isinstance(node, ast.ClassDef):
            if not declared_body_complete(node.body):
                return False
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Pass)):
            continue
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            if any(isinstance(child, ast.Call) for child in ast.walk(node)):
                return False
        else:
            return False
    return True
