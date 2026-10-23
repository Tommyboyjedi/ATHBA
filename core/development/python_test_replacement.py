"""Bounded same-module accepted-test replacement syntax mechanics."""
from __future__ import annotations

import ast
from dataclasses import dataclass

from core.development.python_pytest_adapter import PythonPytestModuleMerger, PythonPytestModuleMergeRequest
from core.development.test_material import TestModuleReplacementRequest


@dataclass(frozen=True)
class _ReplacementAuthority:
    request: TestModuleReplacementRequest
    trusted: ast.Module
    scenario: ast.Module
    names: tuple[str, ...]
    replacement_name: str


class PythonTestModuleReplacement:
    """Remove only explicitly selected functions before the existing safe merge."""

    def replace(self, request: TestModuleReplacementRequest) -> str:
        authority = self._authority(request)
        self._new_imports(authority)
        lines = request.trusted_source.splitlines()
        removals: set[int] = set()
        for node in authority.trusted.body:
            if isinstance(node, ast.FunctionDef) and node.name in authority.names:
                if node.decorator_list:
                    raise ValueError("decorated test replacement is unsupported")
                removals.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        retained = "\n".join(line for index, line in enumerate(lines, 1) if index not in removals)
        result = PythonPytestModuleMerger().merge(PythonPytestModuleMergeRequest(
            retained, request.scenario_source, request.canonical_test_identity))
        self._preserved(authority, result)
        return result

    @staticmethod
    def _identity(identity: str) -> tuple[str, str]:
        path, separator, name = identity.partition("::")
        if not separator or not name or "::" in name:
            raise ValueError("test replacement requires ordinary pytest node identities")
        return path, name

    def _authority(self, request: TestModuleReplacementRequest) -> _ReplacementAuthority:
        path, replacement = self._identity(request.canonical_test_identity)
        identities = tuple(self._identity(item) for item in request.replaced_test_identities)
        if not identities or len(identities) != len(set(identities)) or any(item[0] != path for item in identities):
            raise ValueError("only unique selected tests in the same module can be replaced")
        names = tuple(item[1] for item in identities)
        trusted, scenario = ast.parse(request.trusted_source), ast.parse(request.scenario_source)
        functions = [node for node in trusted.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if any(sum(node.name == name and isinstance(node, ast.FunctionDef) for node in functions) != 1 for name in names):
            raise ValueError("selected accepted test is unknown or ambiguous")
        if any(node.name == replacement and node.name not in names for node in functions):
            raise ValueError("replacement would overwrite an unselected test")
        submitted = [node for node in scenario.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if len(submitted) != 1 or not isinstance(submitted[0], ast.FunctionDef) or submitted[0].name != replacement:
            raise ValueError("replacement must contain exactly its one ordinary test")
        if submitted[0].decorator_list:
            raise ValueError("decorated replacement tests are unsupported")
        return _ReplacementAuthority(request, trusted, scenario, names, replacement)

    @staticmethod
    def _new_imports(authority: _ReplacementAuthority) -> None:
        trusted_nodes = {ast.dump(node, include_attributes=False) for node in authority.trusted.body}
        bound = {node.name for node in authority.trusted.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        assignments = (node for node in authority.trusted.body if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)))
        bound.update(node.id for statement in assignments for node in ast.walk(statement)
                     if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store))
        for node in authority.trusted.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                bound.update(alias.asname or alias.name.partition(".")[0] for alias in node.names)
        for node in authority.scenario.body:
            if isinstance(node, ast.FunctionDef) or ast.dump(node, include_attributes=False) in trusted_nodes:
                continue
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                raise ValueError("new module-level replacement material is unsupported")
            aliases = {alias.asname or alias.name.partition(".")[0] for alias in node.names}
            if "*" in aliases or aliases & bound:
                raise ValueError("replacement import would change an existing module binding")

    @staticmethod
    def _preserved(authority: _ReplacementAuthority, result: str) -> None:
        final = ast.parse(result)
        for node in authority.trusted.body:
            if isinstance(node, ast.FunctionDef) and node.name in authority.names:
                continue
            source = ast.get_source_segment(authority.request.trusted_source, node)
            matches = [candidate for candidate in final.body
                       if ast.dump(candidate, include_attributes=False) == ast.dump(node, include_attributes=False)]
            if len(matches) != 1 or ast.get_source_segment(result, matches[0]) != source:
                raise ValueError("unselected test or module context changed during replacement")
