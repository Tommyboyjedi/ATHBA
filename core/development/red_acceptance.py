from __future__ import annotations

import ast
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Protocol

from core.development.failure_progression import FailureClassification, FailureObservation
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest

if TYPE_CHECKING:
    from core.development.tdd_progression import BehaviorContract, TddStepProposal

TEST_ARTIFACT_DISPOSITIONS = {
    "valid_executable_test",
    "syntax_invalid",
    "collection_failed",
    "target_test_missing",
    "skipped",
    "xfailed",
    "bootstrap_or_fixture_failure",
    "target_not_executed",
    "policy_invalid",
    "unsupported_or_unclassified",
}
PYTEST_OUTCOMES = {
    "failed",
    "passed",
    "skipped",
    "xfailed",
    "xpassed",
    "error",
    "not_run",
}
PHASE_OUTCOMES = {"passed", "failed", "skipped", "not_run"}
RED_VERIFIER_DISPOSITIONS = {
    "valid_red",
    "invalid_test",
    "wrong_behavior",
    "insufficient_evidence",
}
SETUP_FAILURE_PHASES = {"setup", "teardown"}
BROAD_EXCEPTION_TYPES = {"Exception", "BaseException"}
PROBE_MARKER = "athba_red_probe_v1"


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value


def _string_list(values: list[str], label: str) -> list[str]:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")
    return values


def _enum_value(value: str, allowed: set[str], label: str) -> str:
    text = _require_text(str(value), label)
    if text not in allowed:
        raise ValueError(f"unsupported {label}: {text}")
    return text


@dataclass(frozen=True)
class StructuredPytestRedProbe:
    pytest_runtime_available: bool
    collection_succeeded: bool
    requested_node_found: bool
    requested_node_executed: bool
    outcome: str
    reported_node_id: str | None = None
    collected_node_ids: list[str] = field(default_factory=list)
    setup_outcome: str = "not_run"
    call_outcome: str = "not_run"
    teardown_outcome: str = "not_run"
    was_xfail: bool = False
    was_xpass: bool = False
    failure_phase: str | None = None
    exception_type: str | None = None
    failure_message: str | None = None
    traceback_location: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", _enum_value(self.outcome, PYTEST_OUTCOMES, "pytest probe outcome"))
        _string_list(self.collected_node_ids, "pytest probe collected node ids")
        _string_list(self.evidence_refs, "pytest probe evidence refs")
        for label, value in (
            ("pytest probe setup outcome", self.setup_outcome),
            ("pytest probe call outcome", self.call_outcome),
            ("pytest probe teardown outcome", self.teardown_outcome),
        ):
            _enum_value(value, PHASE_OUTCOMES, label)
        for label, value in (
            ("pytest probe reported node id", self.reported_node_id),
            ("pytest probe failure phase", self.failure_phase),
            ("pytest probe exception type", self.exception_type),
            ("pytest probe failure message", self.failure_message),
            ("pytest probe traceback location", self.traceback_location),
        ):
            if value is not None:
                _require_text(value, label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pytest_runtime_available": self.pytest_runtime_available,
            "collection_succeeded": self.collection_succeeded,
            "requested_node_found": self.requested_node_found,
            "requested_node_executed": self.requested_node_executed,
            "outcome": self.outcome,
            "reported_node_id": self.reported_node_id,
            "collected_node_ids": list(self.collected_node_ids),
            "setup_outcome": self.setup_outcome,
            "call_outcome": self.call_outcome,
            "teardown_outcome": self.teardown_outcome,
            "was_xfail": self.was_xfail,
            "was_xpass": self.was_xpass,
            "failure_phase": self.failure_phase,
            "exception_type": self.exception_type,
            "failure_message": self.failure_message,
            "traceback_location": self.traceback_location,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StructuredPytestRedProbe":
        return cls(
            pytest_runtime_available=bool(payload["pytest_runtime_available"]),
            collection_succeeded=bool(payload["collection_succeeded"]),
            requested_node_found=bool(payload["requested_node_found"]),
            requested_node_executed=bool(payload["requested_node_executed"]),
            outcome=str(payload["outcome"]),
            reported_node_id=payload.get("reported_node_id"),
            collected_node_ids=[str(item) for item in payload.get("collected_node_ids", [])],
            setup_outcome=str(payload.get("setup_outcome", "not_run")),
            call_outcome=str(payload.get("call_outcome", "not_run")),
            teardown_outcome=str(payload.get("teardown_outcome", "not_run")),
            was_xfail=bool(payload.get("was_xfail", False)),
            was_xpass=bool(payload.get("was_xpass", False)),
            failure_phase=payload.get("failure_phase"),
            exception_type=payload.get("exception_type"),
            failure_message=payload.get("failure_message"),
            traceback_location=payload.get("traceback_location"),
            stdout=payload.get("stdout"),
            stderr=payload.get("stderr"),
            evidence_refs=[str(item) for item in payload.get("evidence_refs", [])],
        )


@dataclass(frozen=True)
class StaticTestAnalysis:
    parses_successfully: bool
    requested_node_exists: bool
    imported_symbols: list[str] = field(default_factory=list)
    call_targets: list[str] = field(default_factory=list)
    assertion_targets: list[str] = field(default_factory=list)
    skip_markers: list[str] = field(default_factory=list)
    xfail_markers: list[str] = field(default_factory=list)
    broad_exception_handlers: list[str] = field(default_factory=list)
    expected_exception_types: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    syntax_error: str | None = None

    def __post_init__(self) -> None:
        for label, values in (
            ("static imported symbols", self.imported_symbols),
            ("static call targets", self.call_targets),
            ("static assertion targets", self.assertion_targets),
            ("static skip markers", self.skip_markers),
            ("static xfail markers", self.xfail_markers),
            ("static broad exception handlers", self.broad_exception_handlers),
            ("static expected exception types", self.expected_exception_types),
            ("static findings", self.findings),
        ):
            _string_list(values, label)
        if self.syntax_error is not None:
            _require_text(self.syntax_error, "static syntax error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parses_successfully": self.parses_successfully,
            "requested_node_exists": self.requested_node_exists,
            "imported_symbols": list(self.imported_symbols),
            "call_targets": list(self.call_targets),
            "assertion_targets": list(self.assertion_targets),
            "skip_markers": list(self.skip_markers),
            "xfail_markers": list(self.xfail_markers),
            "broad_exception_handlers": list(self.broad_exception_handlers),
            "expected_exception_types": list(self.expected_exception_types),
            "findings": list(self.findings),
            "syntax_error": self.syntax_error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StaticTestAnalysis":
        return cls(
            parses_successfully=bool(payload["parses_successfully"]),
            requested_node_exists=bool(payload["requested_node_exists"]),
            imported_symbols=[str(item) for item in payload.get("imported_symbols", [])],
            call_targets=[str(item) for item in payload.get("call_targets", [])],
            assertion_targets=[str(item) for item in payload.get("assertion_targets", [])],
            skip_markers=[str(item) for item in payload.get("skip_markers", [])],
            xfail_markers=[str(item) for item in payload.get("xfail_markers", [])],
            broad_exception_handlers=[str(item) for item in payload.get("broad_exception_handlers", [])],
            expected_exception_types=[str(item) for item in payload.get("expected_exception_types", [])],
            findings=[str(item) for item in payload.get("findings", [])],
            syntax_error=payload.get("syntax_error"),
        )


@dataclass(frozen=True)
class TestArtifactAssessment:
    disposition: str
    rationale: str
    findings: list[str]
    static_analysis: StaticTestAnalysis
    pytest_probe: StructuredPytestRedProbe
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", _enum_value(self.disposition, TEST_ARTIFACT_DISPOSITIONS, "test artifact disposition"))
        _require_text(self.rationale, "test artifact rationale")
        _string_list(self.findings, "test artifact findings")
        _string_list(self.evidence_refs, "test artifact evidence refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "rationale": self.rationale,
            "findings": list(self.findings),
            "static_analysis": self.static_analysis.to_dict(),
            "pytest_probe": self.pytest_probe.to_dict(),
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TestArtifactAssessment":
        return cls(
            disposition=str(payload["disposition"]),
            rationale=str(payload["rationale"]),
            findings=[str(item) for item in payload.get("findings", [])],
            static_analysis=StaticTestAnalysis.from_dict(dict(payload["static_analysis"])),
            pytest_probe=StructuredPytestRedProbe.from_dict(dict(payload["pytest_probe"])),
            evidence_refs=[str(item) for item in payload.get("evidence_refs", [])],
        )


@dataclass(frozen=True)
class BehaviorEvidence:
    test_node: str
    test_path: str
    source_location: str | None
    imported_symbols: list[str]
    call_targets: list[str]
    assertion_targets: list[str]
    expected_exception_types: list[str]
    target_operation_candidates: list[str]
    runtime_failure_phase: str | None
    runtime_failure_location: str | None
    runtime_exception_type: str | None
    runtime_failure_message: str | None
    target_operation_executed: bool
    findings: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for label, value in (("behavior evidence test node", self.test_node), ("behavior evidence test path", self.test_path)):
            _require_text(value, label)
        for label, values in (
            ("behavior evidence imported symbols", self.imported_symbols),
            ("behavior evidence call targets", self.call_targets),
            ("behavior evidence assertion targets", self.assertion_targets),
            ("behavior evidence expected exception types", self.expected_exception_types),
            ("behavior evidence target operation candidates", self.target_operation_candidates),
            ("behavior evidence findings", self.findings),
            ("behavior evidence refs", self.evidence_refs),
        ):
            _string_list(values, label)
        for label, value in (
            ("behavior evidence source location", self.source_location),
            ("behavior evidence runtime failure phase", self.runtime_failure_phase),
            ("behavior evidence runtime failure location", self.runtime_failure_location),
            ("behavior evidence runtime exception type", self.runtime_exception_type),
            ("behavior evidence runtime failure message", self.runtime_failure_message),
        ):
            if value is not None:
                _require_text(value, label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_node": self.test_node,
            "test_path": self.test_path,
            "source_location": self.source_location,
            "imported_symbols": list(self.imported_symbols),
            "call_targets": list(self.call_targets),
            "assertion_targets": list(self.assertion_targets),
            "expected_exception_types": list(self.expected_exception_types),
            "target_operation_candidates": list(self.target_operation_candidates),
            "runtime_failure_phase": self.runtime_failure_phase,
            "runtime_failure_location": self.runtime_failure_location,
            "runtime_exception_type": self.runtime_exception_type,
            "runtime_failure_message": self.runtime_failure_message,
            "target_operation_executed": self.target_operation_executed,
            "findings": list(self.findings),
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BehaviorEvidence":
        return cls(
            test_node=str(payload["test_node"]),
            test_path=str(payload["test_path"]),
            source_location=payload.get("source_location"),
            imported_symbols=[str(item) for item in payload.get("imported_symbols", [])],
            call_targets=[str(item) for item in payload.get("call_targets", [])],
            assertion_targets=[str(item) for item in payload.get("assertion_targets", [])],
            expected_exception_types=[str(item) for item in payload.get("expected_exception_types", [])],
            target_operation_candidates=[str(item) for item in payload.get("target_operation_candidates", [])],
            runtime_failure_phase=payload.get("runtime_failure_phase"),
            runtime_failure_location=payload.get("runtime_failure_location"),
            runtime_exception_type=payload.get("runtime_exception_type"),
            runtime_failure_message=payload.get("runtime_failure_message"),
            target_operation_executed=bool(payload["target_operation_executed"]),
            findings=[str(item) for item in payload.get("findings", [])],
            evidence_refs=[str(item) for item in payload.get("evidence_refs", [])],
        )


@dataclass(frozen=True)
class RedVerifierResult:
    disposition: str
    rationale: str
    findings: list[str]
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", _enum_value(self.disposition, RED_VERIFIER_DISPOSITIONS, "red verifier disposition"))
        _require_text(self.rationale, "red verifier rationale")
        _string_list(self.findings, "red verifier findings")
        _string_list(self.evidence_refs, "red verifier evidence refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "rationale": self.rationale,
            "findings": list(self.findings),
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RedVerifierResult":
        return cls(
            disposition=str(payload["disposition"]),
            rationale=str(payload["rationale"]),
            findings=[str(item) for item in payload.get("findings", [])],
            evidence_refs=[str(item) for item in payload.get("evidence_refs", [])],
        )


@dataclass(frozen=True)
class RedCandidateAnalysis:
    candidate_change_id: str | None
    candidate_revision: str | None
    trusted_base_revision: str | None
    test_node: str
    artifact_assessment: TestArtifactAssessment
    behavior_evidence: BehaviorEvidence
    verifier_result: RedVerifierResult

    def __post_init__(self) -> None:
        _require_text(self.test_node, "red candidate test node")
        for label, value in (
            ("red candidate change id", self.candidate_change_id),
            ("red candidate revision", self.candidate_revision),
            ("red candidate trusted base", self.trusted_base_revision),
        ):
            if value is not None:
                _require_text(value, label)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_change_id": self.candidate_change_id,
            "candidate_revision": self.candidate_revision,
            "trusted_base_revision": self.trusted_base_revision,
            "test_node": self.test_node,
            "artifact_assessment": self.artifact_assessment.to_dict(),
            "behavior_evidence": self.behavior_evidence.to_dict(),
            "verifier_result": self.verifier_result.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RedCandidateAnalysis":
        return cls(
            candidate_change_id=payload.get("candidate_change_id"),
            candidate_revision=payload.get("candidate_revision"),
            trusted_base_revision=payload.get("trusted_base_revision"),
            test_node=str(payload["test_node"]),
            artifact_assessment=TestArtifactAssessment.from_dict(dict(payload["artifact_assessment"])),
            behavior_evidence=BehaviorEvidence.from_dict(dict(payload["behavior_evidence"])),
            verifier_result=RedVerifierResult.from_dict(dict(payload["verifier_result"])),
        )


@dataclass(frozen=True)
class RedAcceptanceRequest:
    contract: BehaviorContract
    step: TddStepProposal
    repository_root: str
    candidate_revision: str
    trusted_base_revision: str | None
    candidate_change_id: str | None
    evidence_location: str


@dataclass(frozen=True)
class RedVerifierRequest:
    red_request: RedAcceptanceRequest
    assessment: TestArtifactAssessment
    evidence: BehaviorEvidence
    source: str


@dataclass(frozen=True)
class RedAcceptanceDependencies:
    gate: TestArtifactGate = field(default_factory=lambda: TestArtifactGate())
    behavior_analyzer: BehaviorEvidenceAnalyzer = field(default_factory=lambda: BehaviorEvidenceAnalyzer())
    verifier: RedBehaviorVerifier = field(default_factory=lambda: RedBehaviorVerifier())


@dataclass(frozen=True)
class RedAcceptanceResult:
    analysis: RedCandidateAnalysis

    @property
    def is_valid_red(self) -> bool:
        return self.analysis.verifier_result.disposition == "valid_red"

    def as_failure_observation(self) -> FailureObservation:
        disposition = self.analysis.artifact_assessment.disposition
        classification = _classification_for_disposition(disposition, self.analysis.verifier_result.disposition)
        message = self.analysis.verifier_result.rationale
        findings = [*self.analysis.artifact_assessment.findings, *self.analysis.verifier_result.findings]
        return FailureObservation(
            source="athba_red_analysis",
            message=message,
            evidence_refs=[*self.analysis.artifact_assessment.evidence_refs, *self.analysis.behavior_evidence.evidence_refs, *self.analysis.verifier_result.evidence_refs],
            plausible=[classification],
            candidate_revision=self.analysis.candidate_revision,
            status=self.analysis.artifact_assessment.disposition,
            work_unit_id=self.analysis.candidate_change_id,
            phase="red",
            stdout="\n".join(findings) or None,
        )


class GitRevisionReader:
    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root)

    def read(self, revision: str, path: str) -> str:
        normalized = PurePosixPath(path).as_posix()
        result = subprocess.run(
            ["git", "show", f"{revision}:{normalized}"],
            cwd=self.repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git show failed for {normalized}: {detail}")


class PytestProbePacketLoader:
    def load(self, evidence_location: str) -> StructuredPytestRedProbe:
        payload = json.loads(Path(evidence_location).read_text(encoding="utf-8"))
        commands = payload.get("commands", [])
        if not isinstance(commands, list):
            raise ValueError("Rack AI evidence packet commands must be a list")
        for command in commands:
            probe = self._probe_from_command(command)
            if probe is not None:
                return probe
        raise ValueError("Rack AI evidence packet did not contain an ATHBA red probe")

    def _probe_from_command(self, command: object) -> StructuredPytestRedProbe | None:
        if not isinstance(command, dict):
            return None
        if isinstance(command.get("athba_red_probe"), dict):
            return StructuredPytestRedProbe.from_dict(dict(command["athba_red_probe"]))
        for key in ("stdout", "stderr"):
            text = command.get(key)
            if not isinstance(text, str) or PROBE_MARKER not in text:
                continue
            return StructuredPytestRedProbe.from_dict(dict(self._extract_payload(text)))
        return None

    def _extract_payload(self, text: str) -> dict[str, Any]:
        for line in text.splitlines():
            if PROBE_MARKER not in line:
                continue
            _, _, payload = line.partition(PROBE_MARKER)
            return dict(json.loads(payload.strip()))
        raise ValueError("ATHBA red probe marker was missing from command output")


@dataclass(frozen=True)
class StaticNodeFacts:
    imported_symbols: list[str]
    call_targets: list[str]
    assertion_targets: list[str]
    skip_markers: list[str]
    xfail_markers: list[str]
    broad_exception_handlers: list[str]
    expected_exception_types: list[str]


class PythonStaticTestAnalyzer:
    def analyze(self, source: str, test_node: str) -> StaticTestAnalysis:
        function_name = test_node.rsplit("::", 1)[-1]
        try:
            module = ast.parse(source)
        except SyntaxError as error:
            return StaticTestAnalysis(
                parses_successfully=False,
                requested_node_exists=False,
                findings=[f"test source did not parse: {error.msg}"],
                syntax_error=f"{error.msg} at line {error.lineno}",
            )
        function = next((node for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name), None)
        facts = _collect_static_node_facts(function)
        findings = []
        if function is None:
            findings.append("requested pytest node was not defined in the candidate source")
        if facts.broad_exception_handlers:
            findings.append("test swallows broad exceptions and obscures RED evidence")
        return StaticTestAnalysis(
            parses_successfully=True,
            requested_node_exists=function is not None,
            imported_symbols=facts.imported_symbols,
            call_targets=facts.call_targets,
            assertion_targets=facts.assertion_targets,
            skip_markers=facts.skip_markers,
            xfail_markers=facts.xfail_markers,
            broad_exception_handlers=facts.broad_exception_handlers,
            expected_exception_types=facts.expected_exception_types,
            findings=findings,
        )


class TestArtifactGate:
    def __init__(self, dependencies: RedArtifactDependencies | None = None):
        deps = dependencies or RedArtifactDependencies()
        self.packet_loader = deps.packet_loader
        self.static_analyzer = deps.static_analyzer

    def assess(self, request: RedAcceptanceRequest, source: str) -> TestArtifactAssessment:
        probe = self.packet_loader.load(request.evidence_location)
        static = self.static_analyzer.analyze(source, request.step.test_name)
        disposition, rationale, findings = _artifact_disposition(static, probe)
        return TestArtifactAssessment(
            disposition=disposition,
            rationale=rationale,
            findings=findings,
            static_analysis=static,
            pytest_probe=probe,
            evidence_refs=[request.evidence_location, f"pytest-node:{request.step.test_name}"],
        )




@dataclass(frozen=True)
class RedArtifactDependencies:
    packet_loader: PytestProbePacketLoader = field(default_factory=lambda: PytestProbePacketLoader())
    static_analyzer: PythonStaticTestAnalyzer = field(default_factory=lambda: PythonStaticTestAnalyzer())


def _collect_static_node_facts(node: ast.FunctionDef | ast.AsyncFunctionDef | None) -> StaticNodeFacts:
    if node is None:
        return StaticNodeFacts([], [], [], [], [], [], [])
    imported_symbols: set[str] = set()
    call_targets: list[str] = []
    assertion_targets: list[str] = []
    skip_markers: list[str] = []
    xfail_markers: list[str] = []
    broad_exception_handlers: list[str] = []
    expected_exception_types: list[str] = []
    for decorator in node.decorator_list:
        name = _call_name(decorator) or _exception_name(decorator)
        if not name:
            continue
        if "skip" in name:
            skip_markers.append(name)
        if "xfail" in name:
            xfail_markers.append(name)
    for child in ast.walk(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                imported_symbols.add(alias.asname or alias.name)
        if isinstance(child, ast.ImportFrom):
            module = child.module or ""
            for alias in child.names:
                imported_symbols.add(f"{module}.{alias.name}".strip("."))
        if isinstance(child, ast.Call):
            call_name = _call_name(child.func)
            if call_name:
                call_targets.append(call_name)
                if call_name.endswith("pytest.raises") or call_name == "pytest.raises":
                    exception_name = _call_argument_name(child)
                    if exception_name:
                        expected_exception_types.append(exception_name)
                if call_name.endswith("pytest.skip") or call_name == "pytest.skip":
                    skip_markers.append(call_name)
                if call_name.endswith("pytest.xfail") or call_name == "pytest.xfail":
                    xfail_markers.append(call_name)
        if isinstance(child, ast.Try):
            for handler in child.handlers:
                name = _exception_name(handler.type)
                if name in BROAD_EXCEPTION_TYPES or handler.type is None:
                    broad_exception_handlers.append(name or "bare except")
        if isinstance(child, ast.Assert):
            target = ast.unparse(child.test).strip()
            if target:
                assertion_targets.append(target)
    return StaticNodeFacts(
        imported_symbols=sorted(imported_symbols),
        call_targets=call_targets,
        assertion_targets=assertion_targets,
        skip_markers=skip_markers,
        xfail_markers=xfail_markers,
        broad_exception_handlers=broad_exception_handlers,
        expected_exception_types=expected_exception_types,
    )


class BehaviorEvidenceAnalyzer:
    def analyze(self, request: RedAcceptanceRequest, assessment: TestArtifactAssessment) -> BehaviorEvidence:
        static = assessment.static_analysis
        probe = assessment.pytest_probe
        target_candidates = _target_operation_candidates(static.call_targets)
        findings = []
        if not target_candidates:
            findings.append("runtime evidence does not establish that the intended operation executed")
        if not static.assertion_targets and not static.expected_exception_types:
            findings.append("test did not expose a concrete assertion or expected-exception scope")
        return BehaviorEvidence(
            test_node=request.step.test_name,
            test_path=request.step.test_path,
            source_location=f"{request.step.test_path}::{request.step.test_name.rsplit('::', 1)[-1]}",
            imported_symbols=static.imported_symbols,
            call_targets=static.call_targets,
            assertion_targets=static.assertion_targets,
            expected_exception_types=static.expected_exception_types,
            target_operation_candidates=target_candidates,
            runtime_failure_phase=probe.failure_phase,
            runtime_failure_location=probe.traceback_location,
            runtime_exception_type=probe.exception_type,
            runtime_failure_message=probe.failure_message,
            target_operation_executed=probe.requested_node_executed and bool(target_candidates),
            findings=findings,
            evidence_refs=[request.evidence_location, f"behavior:{request.step.test_name}"],
        )


class RedVerifierGateway(Protocol):
    async def reason(self, request: ReasoningRequest):
        ...


class RedBehaviorVerifier:
    def __init__(self, gateway: ReasoningGateway | None = None):
        self.gateway = gateway

    async def verify(self, request: RedVerifierRequest) -> RedVerifierResult:
        if request.assessment.disposition != "valid_executable_test":
            return RedVerifierResult(
                disposition="invalid_test",
                rationale=request.assessment.rationale,
                findings=list(request.assessment.findings),
                evidence_refs=list(request.assessment.evidence_refs),
            )
        if self.gateway is None:
            return self._fallback_verdict(request.assessment, request.evidence)
        reasoning = await self.gateway.reason(
            ReasoningRequest(
                purpose="athba_red_behavior_verifier",
                project_id=request.red_request.contract.project_id,
                requires_large_context=False,
                prompt=_verifier_prompt(request.red_request, request.assessment, request.evidence, request.source),
            )
        )
        return _verifier_result_from_text(reasoning.text, request.assessment.evidence_refs)

    def _fallback_verdict(self, assessment: TestArtifactAssessment, evidence: BehaviorEvidence) -> RedVerifierResult:
        probe = assessment.pytest_probe
        if probe.outcome == "passed":
            return RedVerifierResult(
                disposition="wrong_behavior",
                rationale="the requested test executed but did not fail, so it cannot serve as RED evidence",
                findings=["the candidate test passed instead of exposing an absent or incorrect behavior"],
                evidence_refs=list(assessment.evidence_refs),
            )
        if not evidence.target_operation_executed:
            return RedVerifierResult(
                disposition="insufficient_evidence",
                rationale="runtime evidence does not establish that the intended operation executed",
                findings=list(evidence.findings),
                evidence_refs=list(evidence.evidence_refs),
            )
        if probe.failure_phase in SETUP_FAILURE_PHASES:
            return RedVerifierResult(
                disposition="invalid_test",
                rationale="failure occurred before the behavior under test reached its call phase",
                findings=["failure phase occurred during setup or teardown"],
                evidence_refs=list(evidence.evidence_refs),
            )
        if not evidence.assertion_targets and not evidence.expected_exception_types:
            return RedVerifierResult(
                disposition="insufficient_evidence",
                rationale="the test executed but did not provide a trustworthy assertion or expected-exception scope",
                findings=list(evidence.findings),
                evidence_refs=list(evidence.evidence_refs),
            )
        return RedVerifierResult(
            disposition="valid_red",
            rationale="the valid executable test reached the target operation and failed in the expected RED phase",
            findings=["target node executed", "target operation candidates were observed", "runtime failure remained in the test call phase"],
            evidence_refs=list(evidence.evidence_refs),
        )


class RedAcceptanceService:
    def __init__(self, dependencies: RedAcceptanceDependencies | None = None):
        deps = dependencies or RedAcceptanceDependencies()
        self.gate = deps.gate
        self.behavior_analyzer = deps.behavior_analyzer
        self.verifier = deps.verifier

    async def evaluate(self, request: RedAcceptanceRequest) -> RedAcceptanceResult:
        source = GitRevisionReader(request.repository_root).read(request.candidate_revision, request.step.test_path)
        assessment = self.gate.assess(request, source)
        evidence = self.behavior_analyzer.analyze(request, assessment)
        verdict = await self.verifier.verify(RedVerifierRequest(request, assessment, evidence, source))
        return RedAcceptanceResult(
            analysis=RedCandidateAnalysis(
                candidate_change_id=request.candidate_change_id,
                candidate_revision=request.candidate_revision,
                trusted_base_revision=request.trusted_base_revision,
                test_node=request.step.test_name,
                artifact_assessment=assessment,
                behavior_evidence=evidence,
                verifier_result=verdict,
            )
        )


def _artifact_disposition(static: StaticTestAnalysis, probe: StructuredPytestRedProbe) -> tuple[str, str, list[str]]:
    findings = [*static.findings]
    if not static.parses_successfully:
        return "syntax_invalid", "candidate test source did not parse", findings
    if not probe.pytest_runtime_available:
        findings.append("pytest runtime was unavailable for the requested probe")
        return "unsupported_or_unclassified", "pytest runtime was unavailable", findings
    if not probe.collection_succeeded:
        disposition = "bootstrap_or_fixture_failure" if probe.failure_phase in SETUP_FAILURE_PHASES else "collection_failed"
        findings.append("pytest did not reach clean collection for the requested node")
        return disposition, "collection/bootstrap failed before trustworthy RED analysis", findings
    if not static.requested_node_exists or not probe.requested_node_found:
        findings.append("requested pytest node was not found")
        return "target_test_missing", "the requested pytest node did not exist", findings
    if probe.outcome == "skipped" or static.skip_markers:
        findings.append("the requested test was skipped")
        return "skipped", "skipped tests are not valid RED evidence", findings
    if probe.outcome in {"xfailed", "xpassed"} or static.xfail_markers:
        findings.append("the requested test used xfail/XPASS semantics")
        return "xfailed", "xfail/xpass outcomes are not valid RED evidence", findings
    if probe.failure_phase in SETUP_FAILURE_PHASES:
        findings.append("failure occurred in setup or teardown")
        return "bootstrap_or_fixture_failure", "setup/bootstrap failure is not RED evidence", findings
    if not probe.requested_node_executed:
        findings.append("the requested node never executed")
        return "target_not_executed", "target node execution was not established", findings
    if static.broad_exception_handlers:
        findings.append("the test swallowed broad exceptions")
        return "policy_invalid", "test artifact policy rejected broad exception swallowing", findings
    return "valid_executable_test", "candidate test is a valid executable artifact for semantic RED analysis", findings


def _target_operation_candidates(call_targets: list[str]) -> list[str]:
    return [target for target in call_targets if not target.startswith("pytest.")]


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _call_argument_name(node: ast.Call) -> str | None:
    if not node.args:
        return None
    return _exception_name(node.args[0])


def _exception_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _exception_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _classification_for_disposition(disposition: str, verifier_disposition: str) -> FailureClassification:
    if disposition in {"syntax_invalid"}:
        return FailureClassification.SYNTAX_OR_PARSE_FAILURE
    if disposition in {"collection_failed", "bootstrap_or_fixture_failure", "target_test_missing", "target_not_executed"}:
        return FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE
    if verifier_disposition == "wrong_behavior":
        return FailureClassification.TESTER_CANDIDATE_DEFECT
    return FailureClassification.TESTER_CANDIDATE_DEFECT


def _verifier_prompt(
    request: RedAcceptanceRequest,
    assessment: TestArtifactAssessment,
    evidence: BehaviorEvidence,
    source: str,
) -> str:
    payload = {
        "instruction": "Assess whether this valid executable test is trustworthy RED evidence. Return raw JSON only.",
        "question": "Did this valid executable test genuinely exercise the planned behavior and fail because that behavior is currently absent or incorrect?",
        "behavior_contract": request.contract.to_dict(),
        "tdd_step": request.step.to_dict(),
        "generated_test_source": source,
        "artifact_assessment": assessment.to_dict(),
        "behavior_evidence": evidence.to_dict(),
        "required_output": {
            "disposition": "valid_red|invalid_test|wrong_behavior|insufficient_evidence",
            "rationale": "concise evidence-based explanation",
            "findings": ["descriptive factual findings only"],
            "evidence_refs": ["descriptive evidence refs only"],
        },
        "rules": [
            "return raw JSON only",
            "do not prescribe replacement test code",
            "do not mention production implementation details",
            "fail closed when evidence is insufficient",
            "a passing test is not valid_red",
            "a setup/bootstrap failure is not valid_red",
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _verifier_result_from_text(text: str, default_refs: list[str]) -> RedVerifierResult:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("red verifier response was not valid JSON") from error
    return RedVerifierResult(
        disposition=str(payload["disposition"]),
        rationale=str(payload["rationale"]),
        findings=[str(item) for item in payload.get("findings", [])],
        evidence_refs=[str(item) for item in payload.get("evidence_refs", default_refs)],
    )


def fail_closed_red_acceptance_result(
    *,
    test_node: str,
    candidate_revision: str | None,
    trusted_base_revision: str | None,
    candidate_change_id: str | None,
    evidence_location: str | None,
    rationale: str,
) -> RedAcceptanceResult:
    refs = [item for item in [evidence_location, f"pytest-node:{test_node}"] if item]
    probe = StructuredPytestRedProbe(
        pytest_runtime_available=False,
        collection_succeeded=False,
        requested_node_found=False,
        requested_node_executed=False,
        outcome="not_run",
        failure_phase="collection",
        failure_message=rationale,
        evidence_refs=list(refs),
    )
    assessment = TestArtifactAssessment(
        disposition="unsupported_or_unclassified",
        rationale=rationale,
        findings=[rationale],
        static_analysis=StaticTestAnalysis(parses_successfully=True, requested_node_exists=True),
        pytest_probe=probe,
        evidence_refs=list(refs),
    )
    evidence = BehaviorEvidence(
        test_node=test_node,
        test_path=test_node.split("::", 1)[0],
        source_location=None,
        imported_symbols=[],
        call_targets=[],
        assertion_targets=[],
        expected_exception_types=[],
        target_operation_candidates=[],
        runtime_failure_phase="collection",
        runtime_failure_location=None,
        runtime_exception_type=None,
        runtime_failure_message=rationale,
        target_operation_executed=False,
        findings=[rationale],
        evidence_refs=list(refs),
    )
    verdict = RedVerifierResult(
        disposition="insufficient_evidence",
        rationale=rationale,
        findings=[rationale],
        evidence_refs=list(refs),
    )
    return RedAcceptanceResult(
        analysis=RedCandidateAnalysis(
            candidate_change_id=candidate_change_id,
            candidate_revision=candidate_revision,
            trusted_base_revision=trusted_base_revision,
            test_node=test_node,
            artifact_assessment=assessment,
            behavior_evidence=evidence,
            verifier_result=verdict,
        )
    )


def fallback_red_acceptance_result(
    *,
    test_node: str,
    candidate_revision: str | None,
    trusted_base_revision: str | None,
    candidate_change_id: str | None,
    evidence_location: str | None,
    rationale: str,
) -> RedAcceptanceResult:
    refs = [item for item in [evidence_location, f"pytest-node:{test_node}"] if item]
    probe = StructuredPytestRedProbe(
        pytest_runtime_available=True,
        collection_succeeded=True,
        requested_node_found=True,
        requested_node_executed=True,
        outcome="failed",
        failure_phase="call",
        exception_type="AssertionError",
        failure_message=rationale,
        evidence_refs=list(refs),
    )
    assessment = TestArtifactAssessment(
        disposition="valid_executable_test",
        rationale=rationale,
        findings=[rationale],
        static_analysis=StaticTestAnalysis(parses_successfully=True, requested_node_exists=True),
        pytest_probe=probe,
        evidence_refs=list(refs),
    )
    evidence = BehaviorEvidence(
        test_node=test_node,
        test_path=test_node.split("::", 1)[0],
        source_location=None,
        imported_symbols=[],
        call_targets=[],
        assertion_targets=["legacy-fixture"],
        expected_exception_types=[],
        target_operation_candidates=["legacy-fixture"],
        runtime_failure_phase="call",
        runtime_failure_location=None,
        runtime_exception_type="AssertionError",
        runtime_failure_message=rationale,
        target_operation_executed=True,
        findings=[rationale],
        evidence_refs=list(refs),
    )
    verdict = RedVerifierResult(
        disposition="valid_red",
        rationale=rationale,
        findings=[rationale],
        evidence_refs=list(refs),
    )
    return RedAcceptanceResult(
        analysis=RedCandidateAnalysis(
            candidate_change_id=candidate_change_id,
            candidate_revision=candidate_revision,
            trusted_base_revision=trusted_base_revision,
            test_node=test_node,
            artifact_assessment=assessment,
            behavior_evidence=evidence,
            verifier_result=verdict,
        )
    )
