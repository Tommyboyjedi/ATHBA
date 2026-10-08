"""Selected receiver/call syntax only; no lexical or application semantics."""
from __future__ import annotations

import ast
from pathlib import PurePosixPath

from core.development.semantic_api_annotations import SemanticApiAnnotation
from core.development.scenario_drafting_domain import (
    ScenarioCandidateAssessmentRequest, ScenarioCandidateIssue, ScenarioCandidateIssueCode,
)


def selected_call_shape_issues(request: ScenarioCandidateAssessmentRequest, module: ast.Module) -> tuple[ScenarioCandidateIssue, ...]:
    production = str(PurePosixPath(request.production_path).with_suffix("")).replace("/", ".")
    issues: list[ScenarioCandidateIssue] = []
    for annotation in request.semantic_annotations:
        if annotation.receiver_owner is None or annotation.interaction != "invoke":
            continue
        inspector = _SelectedCallInspector(annotation, production)
        inspector.visit(module)
        issues.extend(inspector.issues)
    return tuple(issues)


class _SelectedCallInspector:
    """Track only syntactically established imports, constructors and local aliases."""

    def __init__(self, annotation: SemanticApiAnnotation, production: str) -> None:
        self.annotation = annotation
        self.production = production
        self.bindings: dict[str, str] = {}
        self.issues: list[ScenarioCandidateIssue] = []

    def visit(self, node: ast.AST) -> None:
        visitor = getattr(self, f"visit_{type(node).__name__}", self._visit_children)
        visitor(node)

    def _visit_children(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.bindings.pop(name, None)
            if alias.name == self.production:
                self.bindings[name] = "module"

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self.bindings.pop(name, None)
            if node.module == self.production:
                if alias.name == self.annotation.receiver_owner:
                    self.bindings[name] = "constructor"
                elif alias.name == self.annotation.symbol:
                    self.bindings[name] = "helper"

    def visit_Assign(self, node: ast.Assign) -> None:
        self.visit(node.value)
        owned = self._owned_receiver(node.value)
        for target in node.targets:
            self._forget(target)
            if isinstance(target, ast.Name) and owned:
                self.bindings[target.id] = "instance"

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        owned = node.value is not None and self._owned_receiver(node.value)
        self._forget(node.target)
        if isinstance(node.target, ast.Name) and owned:
            self.bindings[node.target.id] = "instance"

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.bindings.pop(node.name, None)
        previous = self.bindings
        self.bindings = previous.copy()
        self._forget(node)
        for argument in ast.walk(node.args):
            if isinstance(argument, ast.arg):
                self.bindings.pop(argument.arg, None)
        for statement in node.body:
            self.visit(statement)
        self.bindings = previous

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        direct = isinstance(function, ast.Name) and self.bindings.get(function.id) == "helper"
        member = isinstance(function, ast.Attribute) and function.attr == self.annotation.symbol
        module_call = isinstance(function, ast.Attribute) and member and isinstance(function.value, ast.Name) and self.bindings.get(function.value.id) == "module"
        if direct or module_call:
            self._issue("The selected behavior is an instance operation; a module/free helper does not demonstrate its receiver form.")
        elif isinstance(function, ast.Attribute) and member and self._owned_receiver(function.value) and self.annotation.argument_count is not None:
            expanded = any(isinstance(arg, ast.Starred) for arg in node.args) or any(arg.arg is None for arg in node.keywords)
            count = len(node.args) + len(node.keywords)
            if expanded or count != self.annotation.argument_count:
                self._issue(f"The selected behavior requires {self.annotation.argument_count} explicit arguments; "
                            f"this call has {'unresolved argument expansion' if expanded else str(count)}. "
                            "Demonstrate the selected call shape without adding arguments or inferring parameter spellings.")
        self._visit_children(node)

    def _owned_receiver(self, expression: ast.AST) -> bool:
        if isinstance(expression, ast.Name):
            return self.bindings.get(expression.id) == "instance"
        if not isinstance(expression, ast.Call):
            return False
        function = expression.func
        if isinstance(function, ast.Name):
            return self.bindings.get(function.id) == "constructor"
        return (isinstance(function, ast.Attribute) and function.attr == self.annotation.receiver_owner
                and isinstance(function.value, ast.Name) and self.bindings.get(function.value.id) == "module")

    def _forget(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                self.bindings.pop(child.id, None)

    def _uncertain_scope(self, node: ast.AST) -> None:
        self._forget(node)
        for call in (child for child in ast.walk(node) if isinstance(child, ast.Call)):
            self.visit_Call(call)

    visit_If = _uncertain_scope
    visit_For = _uncertain_scope
    visit_AsyncFor = _uncertain_scope
    visit_While = _uncertain_scope
    visit_Try = _uncertain_scope
    visit_With = _uncertain_scope
    visit_AsyncWith = _uncertain_scope
    visit_ListComp = _uncertain_scope
    visit_SetComp = _uncertain_scope
    visit_DictComp = _uncertain_scope
    visit_GeneratorExp = _uncertain_scope
    visit_AugAssign = _uncertain_scope
    visit_NamedExpr = _uncertain_scope
    visit_Delete = _forget

    def _issue(self, message: str) -> None:
        self.issues.append(ScenarioCandidateIssue(ScenarioCandidateIssueCode.BEHAVIOR_CALL_SHAPE.value, message))
