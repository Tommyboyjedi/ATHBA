"""Python/pytest implementation of the strict-TDD language adapter."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from core.development.microcycle_domain import (
    BoundaryAssessment, BoundaryClassificationRequest, BoundaryDiagnostic,
    BoundaryOutcome, DiagnosticFact, FinalTestMaterialisationRequest,
    FragmentSourceSpan, FragmentationRequest, FrontierExecutionRequest,
    FrontierMaterialisationRequest, LanguageAdapterDescriptor, MaterialisedTestArtifact,
    RegressionContract, RegressionContractRequest, ScenarioFragment, ScenarioModel,
    ScenarioParseRequest, SourceSpan, SyntaxValidationRequest,
)

PYTHON_LANGUAGE_ID = "python"
PYTEST_ADAPTER_VERSION = "1.0.0"


class PythonFragmentKind(str, Enum):
    PRODUCTION_IMPORT = "production_import"
    DECLARATION = "declaration"
    CONSTRUCTOR = "constructor"
    CALL = "call"
    ASSERTION = "assertion"
    RAISES_BLOCK = "raises_block"
    IF_BLOCK = "if_block"
    LOOP_BLOCK = "loop_block"
    WITH_BLOCK = "with_block"
    TRY_BLOCK = "try_block"


@dataclass(frozen=True)
class _Node:
    kind: PythonFragmentKind
    source: str
    source_span: SourceSpan
    module_scope: bool
    capability: str


@dataclass(frozen=True)
class _NodeRequest:
    source: str
    node: ast.stmt
    module_scope: bool


@dataclass(frozen=True)
class _Emission:
    fragment: ScenarioFragment
    source: str
    indent: str


@dataclass
class _Buffer:
    rows: list[str]
    spans: list[FragmentSourceSpan]


@dataclass(frozen=True)
class _Parsed:
    scaffolding: tuple[str, ...]
    header: str
    nodes: tuple[_Node, ...]


class PythonScenarioParser:
    """Parses one ordinary pytest test and rejects dynamic or ambiguous drafts."""

    def parse(self, source: str) -> _Parsed:
        try:
            module = ast.parse(source)
        except SyntaxError as error:
            raise ValueError(f"unsupported or invalid Python scenario syntax: {error.msg}") from error
        functions = [node for node in module.body if isinstance(node, ast.FunctionDef)]
        if len(functions) != 1 or any(not isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)) for node in module.body):
            raise ValueError("supported scenarios contain module imports and exactly one test function")
        function = functions[0]
        if not function.name.startswith("test_") or any(self._is_parameterize(item) for item in function.decorator_list):
            raise ValueError("unsupported dynamic test generation")
        if any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Yield, ast.YieldFrom, ast.Await)) for node in ast.walk(function) if node is not function):
            raise ValueError("unsupported dynamic test form")
        lines = source.splitlines()
        first_body = function.body[0].lineno if function.body else (function.end_lineno or function.lineno) + 1
        header_start = min([function.lineno, *(item.lineno for item in function.decorator_list)])
        header = "\n".join(lines[header_start - 1:first_body - 1])
        scaffolding, nodes = [], []
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                continue
            if self._is_pytest_import(node):
                scaffolding.append(self._source(source, node))
            else:
                nodes.append(self._node(_NodeRequest(source, node, True)))
        for node in function.body:
            if self._is_pytest_import(node):
                scaffolding.append(self._source(source, node))
            else:
                nodes.append(self._node(_NodeRequest(source, node, False)))
        if not nodes:
            raise ValueError("scenario must contain at least one behavior fragment")
        return _Parsed(tuple(scaffolding), header, tuple(nodes))

    def _node(self, request: _NodeRequest) -> _Node:
        kind = self._kind(request.node)
        return _Node(kind, self._source(request.source, request.node), SourceSpan(request.node.lineno, request.node.end_lineno or request.node.lineno), request.module_scope, self._capability(request.node))

    @staticmethod
    def _source(source: str, node: ast.AST) -> str:
        value = ast.get_source_segment(source, node)
        if not value:
            raise ValueError("parser could not recover a complete source fragment")
        return textwrap.dedent(value).strip("\n")

    @staticmethod
    def _is_pytest_import(node: ast.stmt) -> bool:
        return isinstance(node, ast.Import) and any(item.name == "pytest" for item in node.names) or isinstance(node, ast.ImportFrom) and node.module == "pytest"

    @staticmethod
    def _is_parameterize(node: ast.expr) -> bool:
        return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "parametrize"

    @staticmethod
    def _kind(node: ast.stmt) -> PythonFragmentKind:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return PythonFragmentKind.PRODUCTION_IMPORT
        if isinstance(node, ast.Assert):
            return PythonFragmentKind.ASSERTION
        if isinstance(node, ast.With):
            return PythonFragmentKind.RAISES_BLOCK if any(PythonScenarioParser._is_raises(item.context_expr) for item in node.items) else PythonFragmentKind.WITH_BLOCK
        if isinstance(node, ast.If):
            return PythonFragmentKind.IF_BLOCK
        if isinstance(node, (ast.For, ast.While)):
            return PythonFragmentKind.LOOP_BLOCK
        if isinstance(node, ast.Try):
            return PythonFragmentKind.TRY_BLOCK
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            return PythonFragmentKind.CONSTRUCTOR
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return PythonFragmentKind.CALL
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            return PythonFragmentKind.DECLARATION
        raise ValueError(f"unsupported Python statement form: {type(node).__name__}")

    @staticmethod
    def _is_raises(expression: ast.expr) -> bool:
        return isinstance(expression, ast.Call) and isinstance(expression.func, ast.Attribute) and expression.func.attr == "raises"

    @staticmethod
    def _capability(node: ast.stmt) -> str:
        if isinstance(node, ast.Import):
            return node.names[0].name
        if isinstance(node, ast.ImportFrom):
            return node.names[0].name
        call = node.value if isinstance(node, (ast.Assign, ast.Expr)) else None
        if isinstance(call, ast.Call):
            if isinstance(call.func, ast.Name):
                return call.func.id
            if isinstance(call.func, ast.Attribute):
                return call.func.attr
        return type(node).__name__


class PythonFrontierMaterialiser:
    """Emits complete modules and maps each emitted fragment to artifact lines."""

    def materialise(self, request: FrontierMaterialisationRequest) -> MaterialisedTestArtifact:
        parsed = PythonScenarioParser().parse(request.model.complete_source)
        if len(parsed.nodes) != len(request.fragments):
            raise ValueError("fragments do not match the approved Python scenario")
        selected_ids = set(request.frontier.materialised_fragment_ids)
        rows: list[str] = []
        spans: list[FragmentSourceSpan] = []
        buffer = _Buffer(rows, spans)
        self._append_scaffolding(rows, parsed.scaffolding)
        for index, node in enumerate(parsed.nodes):
            fragment = request.fragments[index]
            if node.module_scope and fragment.fragment_id in selected_ids:
                self._append_fragment(buffer, _Emission(fragment, node.source, ""))
        if rows:
            rows.append("")
        rows.extend(parsed.header.splitlines())
        body = [(request.fragments[index], node) for index, node in enumerate(parsed.nodes) if not node.module_scope and request.fragments[index].fragment_id in selected_ids]
        if not body:
            rows.append("    pass")
        for fragment, node in body:
            self._append_fragment(buffer, _Emission(fragment, node.source, "    "))
        source = "\n".join(rows) + "\n"
        active = request.frontier.active_fragment_id
        if active not in {item.fragment_id for item in request.fragments}:
            raise ValueError("active frontier fragment is unknown")
        return MaterialisedTestArtifact(
            "python-pytest", PYTEST_ADAPTER_VERSION, request.model.scenario_id,
            request.frontier.index, request.model.canonical_test_identity, source,
            active, tuple(spans), request.base_revision,
        )

    @staticmethod
    def _append_scaffolding(rows: list[str], scaffolding: tuple[str, ...]) -> None:
        for source in scaffolding:
            rows.extend(source.splitlines())

    @staticmethod
    def _append_fragment(buffer: _Buffer, emission: _Emission) -> None:
        start = len(buffer.rows) + 1
        buffer.rows.extend(textwrap.indent(emission.source, emission.indent).splitlines())
        buffer.spans.append(FragmentSourceSpan(emission.fragment.fragment_id, SourceSpan(start, len(buffer.rows))))


class PytestStructuredExecutor:
    """Runs pytest through hooks and converts facts without trusting console wording."""

    def execute(self, request: FrontierExecutionRequest) -> BoundaryDiagnostic:
        root = Path(request.project_root).resolve()
        path = (root / request.test_path).resolve()
        if root not in path.parents:
            return BoundaryDiagnostic("infrastructure", "test path escapes project root")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(request.artifact.complete_source, encoding="utf-8")
        self._invalidate_module_cache(path)
        syntax = self._syntax(path, request.test_path)
        if syntax is not None:
            return syntax
        node = request.artifact.canonical_test_identity
        command = [sys.executable, "-m", "core.development.python_pytest_probe", str(root), node]
        environment = os.environ | {"PYTHONPATH": str(Path(__file__).resolve().parents[2])}
        completed = subprocess.run(command, capture_output=True, text=True, env=environment, timeout=30)
        try:
            facts = json.loads(completed.stdout.splitlines()[-1])
        except json.JSONDecodeError:
            return BoundaryDiagnostic("infrastructure", "structured pytest probe did not return JSON", ("pytest-probe",))
        return self._diagnostic(facts)

    @staticmethod
    def _invalidate_module_cache(path: Path) -> None:
        cache = path.parent / "__pycache__"
        for entry in cache.glob(f"{path.stem}.*.pyc") if cache.exists() else ():
            entry.unlink()

    @staticmethod
    def _syntax(path: Path, test_path: str) -> BoundaryDiagnostic | None:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as error:
            return BoundaryDiagnostic("syntax_error", error.msg, (test_path,), (DiagnosticFact("source_line", str(error.lineno or 0)),))
        return None

    @staticmethod
    def _diagnostic(facts: dict[str, object]) -> BoundaryDiagnostic:
        pairs = tuple(DiagnosticFact(str(name), str(value)) for name, value in facts.items() if value not in (None, "", [], False))
        evidence_value = facts.get("evidence_refs", ())
        evidence = tuple(str(item) for item in evidence_value) if isinstance(evidence_value, list) else ()
        outcome = str(facts.get("outcome", "error"))
        message = str(facts.get("failure_message") or outcome)
        if outcome == "passed":
            return BoundaryDiagnostic("green", message, evidence, pairs)
        if not facts.get("collection_succeeded", False):
            return BoundaryDiagnostic("collection_failure", message, evidence, pairs)
        return BoundaryDiagnostic("pytest_failure", message, evidence, pairs)


class PythonBoundaryClassifier:
    """Accepts only evidence at the active complete Python fragment."""

    def classify(self, request: BoundaryClassificationRequest) -> BoundaryAssessment:
        facts = {item.name: item.value for item in request.diagnostic.facts}
        if request.diagnostic.kind == "green":
            return BoundaryAssessment(BoundaryOutcome.GREEN.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.diagnostic.kind == "syntax_error":
            return BoundaryAssessment(BoundaryOutcome.INVALID_TEST_SYNTAX.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.diagnostic.kind == "infrastructure":
            return BoundaryAssessment(BoundaryOutcome.INFRASTRUCTURE_FAILURE.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.prior_frontier_status not in (None, BoundaryOutcome.GREEN.value) or not self._at_active_span(request, facts):
            return BoundaryAssessment(BoundaryOutcome.FAILURE_BEFORE_FRONTIER.value, request.active_fragment.fragment_id, request.diagnostic)
        if request.diagnostic.kind == "collection_failure":
            outcome = BoundaryOutcome.VALID_MISSING_CAPABILITY_RED if request.active_fragment.kind == PythonFragmentKind.PRODUCTION_IMPORT.value else BoundaryOutcome.FAILURE_BEFORE_FRONTIER
            return BoundaryAssessment(outcome.value, request.active_fragment.fragment_id, request.diagnostic)
        exception = facts.get("exception_type", "")
        active_kind = request.active_fragment.kind
        if exception in {"ImportError", "ModuleNotFoundError", "NameError", "AttributeError"} and active_kind in {item.value for item in (PythonFragmentKind.PRODUCTION_IMPORT, PythonFragmentKind.CONSTRUCTOR, PythonFragmentKind.CALL)}:
            return BoundaryAssessment(BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value, request.active_fragment.fragment_id, request.diagnostic)
        if active_kind == PythonFragmentKind.ASSERTION and exception == "AssertionError":
            return BoundaryAssessment(BoundaryOutcome.VALID_BEHAVIORAL_RED.value, request.active_fragment.fragment_id, request.diagnostic)
        if active_kind == PythonFragmentKind.RAISES_BLOCK and "DID NOT RAISE" in request.diagnostic.message:
            return BoundaryAssessment(BoundaryOutcome.VALID_BEHAVIORAL_RED.value, request.active_fragment.fragment_id, request.diagnostic)
        return BoundaryAssessment(BoundaryOutcome.UNSUPPORTED_LANGUAGE_BOUNDARY.value, request.active_fragment.fragment_id, request.diagnostic)

    @staticmethod
    def _at_active_span(request: BoundaryClassificationRequest, facts: dict[str, str]) -> bool:
        line = int(facts.get("source_line", "0"))
        for span in request.artifact.fragment_source_spans:
            if span.fragment_id == request.active_fragment.fragment_id:
                return span.span.start_line <= line <= span.span.end_line
        return False


class PythonPytestAdapter:
    descriptor = LanguageAdapterDescriptor("python-pytest", PYTEST_ADAPTER_VERSION, PYTHON_LANGUAGE_ID)

    def parse_scenario(self, request: ScenarioParseRequest) -> ScenarioModel:
        if request.draft.language_id != PYTHON_LANGUAGE_ID:
            raise ValueError("unsupported language boundary")
        PythonScenarioParser().parse(request.draft.source)
        return ScenarioModel(request.draft.scenario_id, PYTHON_LANGUAGE_ID, PYTEST_ADAPTER_VERSION, request.draft.canonical_test_identity, request.draft.source, request.draft.test_path)

    def validate_scenario_syntax(self, request: SyntaxValidationRequest) -> bool:
        PythonScenarioParser().parse(request.model.complete_source)
        return True

    def fragment_scenario(self, request: FragmentationRequest) -> tuple[ScenarioFragment, ...]:
        parsed = PythonScenarioParser().parse(request.model.complete_source)
        result: list[ScenarioFragment] = []
        for index, node in enumerate(parsed.nodes):
            result.append(ScenarioFragment(f"python-{index + 1}-{node.kind.value}", request.model.scenario_id, node.kind.value, node.source, node.capability, tuple(item.fragment_id for item in result), node.source_span))
        return tuple(result)

    def materialise_frontier(self, request: FrontierMaterialisationRequest) -> MaterialisedTestArtifact:
        return PythonFrontierMaterialiser().materialise(request)

    def execute_frontier(self, request: FrontierExecutionRequest) -> BoundaryDiagnostic:
        return PytestStructuredExecutor().execute(request)

    def classify_boundary(self, request: BoundaryClassificationRequest) -> BoundaryAssessment:
        return PythonBoundaryClassifier().classify(request)

    def materialise_final_test(self, request: FinalTestMaterialisationRequest) -> MaterialisedTestArtifact:
        fragments = request.fragments
        frontier = type("FinalFrontier", (), {"index": len(fragments) - 1, "active_fragment_id": fragments[-1].fragment_id, "materialised_fragment_ids": tuple(item.fragment_id for item in fragments)})()
        return self.materialise_frontier(FrontierMaterialisationRequest(request.model, fragments, frontier, request.base_revision))

    def regression_contract(self, request: RegressionContractRequest) -> RegressionContract:
        return RegressionContract((sys.executable, "-m", "pytest", "-q"))
