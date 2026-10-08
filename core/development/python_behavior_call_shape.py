"""Selected receiver syntax only; no lexical identifier or implementation semantics."""
from __future__ import annotations

import ast
from pathlib import PurePosixPath

from core.development.scenario_drafting_domain import (
    ScenarioCandidateAssessmentRequest, ScenarioCandidateIssue, ScenarioCandidateIssueCode,
)


def selected_call_shape_issues(request: ScenarioCandidateAssessmentRequest, module: ast.Module) -> tuple[ScenarioCandidateIssue, ...]:
    production = str(PurePosixPath(request.production_path).with_suffix("")).replace("/", ".")
    modules = {alias.asname or alias.name for node in module.body if isinstance(node, ast.Import)
               for alias in node.names if alias.name == production}
    functions = {alias.asname or alias.name: alias.name for node in module.body
                 if isinstance(node, ast.ImportFrom) and node.module == production for alias in node.names}
    issues: list[ScenarioCandidateIssue] = []
    for annotation in request.semantic_annotations:
        if annotation.receiver_owner is None or annotation.interaction != "invoke":
            continue
        for call in (node for node in ast.walk(module) if isinstance(node, ast.Call)):
            direct = isinstance(call.func, ast.Name) and functions.get(call.func.id) == annotation.symbol
            module_call = (isinstance(call.func, ast.Attribute) and call.func.attr == annotation.symbol
                           and isinstance(call.func.value, ast.Name) and call.func.value.id in modules)
            if direct or module_call:
                issues.append(ScenarioCandidateIssue(
                    ScenarioCandidateIssueCode.BEHAVIOR_CALL_SHAPE.value,
                    "The selected behavior is an instance operation; a module/free helper does not demonstrate its receiver form.",
                ))
    return tuple(issues)
