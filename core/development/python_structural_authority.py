"""Bounded equivalence proof for the Python adapter's data/call collision."""
from __future__ import annotations

import ast
import copy

from core.development.structural_refactor_domain import StructuralCandidateCheck, StructuralProductionSource


def valid_structural_candidate(request: StructuralCandidateCheck) -> bool:
    """Require preserved existing logic, a state relocation and a thin accessor.

    This is a conservative adapter proof, not authority for arbitrary new logic.
    Other languages supply their own equivalence checks through the same port.
    """
    try:
        old = ast.parse(request.original_source)
        new = ast.parse(request.candidate_source)
    except SyntaxError:
        return False
    scopes = [node for node in old.body if isinstance(node, ast.ClassDef)
              and node.lineno == request.problem.scope_start
              and node.end_lineno == request.problem.scope_end]
    if len(scopes) != 1:
        return False
    original = scopes[0]
    matches = [node for node in new.body if isinstance(node, ast.ClassDef) and node.name == original.name]
    if len(matches) != 1:
        return False
    candidate = matches[0]
    if _outside(old, original) != _outside(new, candidate):
        return False
    subject = request.problem.subject
    accessor = [node for node in candidate.body if isinstance(node, ast.FunctionDef) and node.name == subject]
    if len(accessor) != 1:
        return False
    method = accessor[0]
    if method.decorator_list or len(method.args.args) != 1 or method.args.posonlyargs:
        return False
    if method.args.vararg or method.args.kwarg or method.args.kwonlyargs or method.args.defaults:
        return False
    if len(method.body) != 1 or not isinstance(method.body[0], ast.Return):
        return False
    value = method.body[0].value
    receiver = method.args.args[0].arg
    original_attributes = {node.attr for node in ast.walk(original) if isinstance(node, ast.Attribute)}
    candidate_attributes = {node.attr for node in ast.walk(candidate) if isinstance(node, ast.Attribute)}
    relocations = candidate_attributes - original_attributes
    if len(relocations) != 1:
        return False
    relocated = next(iter(relocations))
    if not relocated.startswith("_"):
        return False
    expected = copy.deepcopy(original)
    for node in ast.walk(expected):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.attr == subject:
            node.attr = relocated
    retained = copy.deepcopy(candidate)
    retained.body = [node for node in retained.body if not isinstance(node, ast.FunctionDef) or node.name != subject]
    if ast.dump(expected) != ast.dump(retained):
        return False
    if isinstance(value, ast.Attribute):
        return isinstance(value.value, ast.Name) and value.value.id == receiver and value.attr == relocated
    if isinstance(value, ast.Call) and not value.args and not value.keywords and isinstance(value.func, ast.Attribute):
        if not isinstance(value.func.value, ast.Name) or value.func.value.id != receiver:
            return False
        getters = [node for node in expected.body if isinstance(node, ast.FunctionDef) and node.name == value.func.attr]
        if len(getters) == 1:
            getter = getters[0]
            return (len(getter.args.args) == 1 and not getter.decorator_list
                    and len(getter.body) == 1 and isinstance(getter.body[0], ast.Return)
                    and isinstance(getter.body[0].value, ast.Attribute)
                    and getter.body[0].value.attr == relocated
                    and isinstance(getter.body[0].value.value, ast.Name)
                    and getter.body[0].value.value.id == getter.args.args[0].arg)
    return False


def _outside(module: ast.Module, scope: ast.ClassDef) -> str:
    result = copy.deepcopy(module)
    result.body = [node for node in result.body if not isinstance(node, ast.ClassDef) or node.name != scope.name]
    return ast.dump(result)


def focused_structural_source(request: StructuralProductionSource) -> str:
    module = ast.parse(request.source)
    scope = next(node for node in module.body if isinstance(node, ast.ClassDef)
                 and node.lineno == request.problem.scope_start and node.end_lineno == request.problem.scope_end)
    lines = request.source.splitlines(keepends=True)
    source = "".join(lines[scope.lineno - 1:scope.body[0].lineno - 1])
    for node in scope.body:
        relevant = any(
            isinstance(item, ast.Attribute) and item.attr == request.problem.subject
            or isinstance(item, ast.Name) and item.id == request.problem.subject
            for item in ast.walk(node)
        )
        if relevant:
            start = min([node.lineno, *(item.lineno for item in getattr(node, "decorator_list", ()))])
            source += "".join(lines[start - 1:node.end_lineno]) + "\n"
    return source.rstrip() + "\n"
