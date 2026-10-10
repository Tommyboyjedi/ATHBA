"""Python syntax and pytest command mechanics, selected only at composition."""
from __future__ import annotations
import ast
import sys
from core.development.test_material import TestModuleMergeRequest, TestSourceRequest
from core.development.python_pytest_adapter import PythonPytestModuleMerger, PythonPytestModuleMergeRequest


class PythonTestMaterial:
    adapter_id = "python-pytest"
    language_id = "python"
    framework = "pytest"

    def merge(self, request: TestModuleMergeRequest) -> str:
        return PythonPytestModuleMerger().merge(PythonPytestModuleMergeRequest(
            request.trusted_source, request.scenario_source, request.canonical_test_identity))

    def extract(self, request: TestSourceRequest) -> str | None:
        function = request.identity.partition("::")[2]
        if not function or "::" in function:
            return None
        try:
            tree = ast.parse(request.source)
        except SyntaxError:
            return None
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
                segment = ast.get_source_segment(request.source, node)
                return None if segment is None else segment.strip()
        return None

    def test_path(self, identity: str) -> str:
        path, separator, function = identity.partition("::")
        if not separator or not function or "::" in function:
            raise ValueError("test identity is not a supported pytest node")
        return path

    def acceptance_command(self, identity: str) -> list[str]:
        return [sys.executable, "-m", "pytest", "-q", identity]

    def syntax_command(self, path: str) -> list[str]:
        return ["python3", "-B", "-m", "py_compile", path]
