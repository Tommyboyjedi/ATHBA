"""Persistent records for bounded Tester scenario drafting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from core.development.microcycle_domain import (
    MicrocycleState,
    ScenarioIntentResult,
    ScenarioSourceCandidate,
    ScenarioStaticAnalysis,
    SourceSpan,
)
from core.development.tdd_progression import TddStepProposal
from core.development.work_unit import WorkerExecutionProvenance

MAX_TESTER_SCENARIO_ATTEMPTS = 4
MAX_SCENARIO_CANDIDATE_SOURCE_CHARACTERS = 65536


class ScenarioCandidateIssueCode(str, Enum):
    SYNTAX_INVALID = "syntax_invalid"
    MODULE_DOCSTRING = "module_docstring"
    NO_TEST = "no_test"
    MULTIPLE_TESTS = "multiple_tests"
    HELPER_FUNCTION = "helper_function"
    FIXTURE = "fixture"
    TEST_CLASS = "test_class"
    ASYNC_TEST = "async_test"
    PARAMETERIZED_TEST = "parameterized_test"
    UNSUPPORTED_TOP_LEVEL = "unsupported_top_level"
    UNSUPPORTED_NESTED = "unsupported_nested"
    MISSING_PRODUCTION_REFERENCE = "missing_production_reference"
    SUBSTITUTE_IMPLEMENTATION = "substitute_implementation"
    MOCKED_BEHAVIOR = "mocked_behavior"
    SKIP_OR_XFAIL = "skip_or_xfail"
    MISSING_CAPABILITY_EVASION = "missing_capability_evasion"
    TEST_FUNCTION_DOCSTRING = "test_function_docstring"
    STANDALONE_STRING_EXPRESSION = "standalone_string_expression"
    CANDIDATE_UNCHANGED = "candidate_unchanged"


class ScenarioCandidateUnchangedDisposition(str, Enum):
    SAME_REVISION = "same_revision"
    SAME_SOURCE = "same_source"
    SAME_REVISION_AND_SOURCE = "same_revision_and_source"


@dataclass(frozen=True)
class ScenarioCandidateUnchangedEvidence:
    """Persisted comparison proving a repair did not change the candidate."""
    previous_revision: str
    returned_revision: str
    previous_source_digest: str | None
    returned_source_digest: str | None
    disposition: str
    def to_dict(self) -> dict[str, object]:
        return asdict(self)
    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioCandidateUnchangedEvidence":
        return cls(str(value["previous_revision"]), str(value["returned_revision"]), value.get("previous_source_digest"), value.get("returned_source_digest"), str(value["disposition"]))


@dataclass(frozen=True)
class ScenarioAuthoringContract:
    """Typed strict grammar shared by authoring and deterministic validation."""

    language_id: str
    framework: str
    required_test_count: int
    allowed_top_level_forms: tuple[str, ...]
    prohibited_top_level_forms: tuple[str, ...]
    prohibited_test_forms: tuple[str, ...]
    requires_direct_production_reference: bool
    prohibits_substitute_implementation: bool
    prohibits_behavior_mocking: bool
    prohibits_skip_or_xfail: bool
    canonical_identity_policy: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioCandidateIssue:
    code: str
    detail: str
    source_span: SourceSpan | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "detail": self.detail,
            "source_span": None if self.source_span is None else self.source_span.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioCandidateIssue":
        span = value.get("source_span")
        return cls(str(value["code"]), str(value["detail"]), None if span is None else SourceSpan.from_dict(dict(span)))


@dataclass(frozen=True)
class ScenarioCandidateAssessment:
    """Typed persisted facts and repair instructions for a submitted candidate."""

    syntax_valid: bool
    actual_test_identities: tuple[str, ...]
    helper_function_names: tuple[str, ...] = ()
    fixture_names: tuple[str, ...] = ()
    class_names: tuple[str, ...] = ()
    async_test_names: tuple[str, ...] = ()
    parameterized_test_names: tuple[str, ...] = ()
    module_docstring_present: bool = False
    unsupported_top_level_nodes: tuple[str, ...] = ()
    unsupported_nested_nodes: tuple[str, ...] = ()
    production_reference_paths: tuple[str, ...] = ()
    substitute_definitions: tuple[str, ...] = ()
    mocked_behavior_targets: tuple[str, ...] = ()
    evasion_markers: tuple[str, ...] = ()
    issues: tuple[ScenarioCandidateIssue, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.syntax_valid and not self.issues

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "issues": [item.to_dict() for item in self.issues]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioCandidateAssessment":
        return cls(
            syntax_valid=bool(value.get("syntax_valid", False)),
            actual_test_identities=tuple(value.get("actual_test_identities", ())),
            helper_function_names=tuple(value.get("helper_function_names", ())),
            fixture_names=tuple(value.get("fixture_names", ())),
            class_names=tuple(value.get("class_names", ())),
            async_test_names=tuple(value.get("async_test_names", ())),
            parameterized_test_names=tuple(value.get("parameterized_test_names", ())),
            module_docstring_present=bool(value.get("module_docstring_present", False)),
            unsupported_top_level_nodes=tuple(value.get("unsupported_top_level_nodes", ())),
            unsupported_nested_nodes=tuple(value.get("unsupported_nested_nodes", ())),
            production_reference_paths=tuple(value.get("production_reference_paths", ())),
            substitute_definitions=tuple(value.get("substitute_definitions", ())),
            mocked_behavior_targets=tuple(value.get("mocked_behavior_targets", ())),
            evasion_markers=tuple(value.get("evasion_markers", ())),
            issues=tuple(ScenarioCandidateIssue.from_dict(dict(item)) for item in value.get("issues", ())),
        )

    def repair_feedback(self) -> str:
        if not self.issues:
            return "candidate satisfies the strict authoring contract"
        return " ".join(item.detail for item in self.issues)


@dataclass(frozen=True)
class ScenarioCandidateAssessmentRequest:
    candidate: ScenarioSourceCandidate
    production_path: str
    contract: ScenarioAuthoringContract


class ScenarioDraftStatus(str, Enum):
    DRAFTING = "drafting"
    APPROVED = "approved"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


@dataclass(frozen=True)
class ScenarioRepositoryFacts:
    trusted_revision: str
    visible_paths: tuple[str, ...]
    production_excerpt: str
    test_excerpt: str

    def __post_init__(self) -> None:
        if not self.trusted_revision.strip():
            raise ValueError("repository facts require a trusted revision")
        if any(not item.strip() for item in self.visible_paths):
            raise ValueError("repository paths must be non-empty")


@dataclass(frozen=True)
class ScenarioDraftRequest:
    scenario_id: str
    ticket: TddStepProposal
    source_requirement_refs: tuple[str, ...]
    language_id: str
    test_framework: str
    allowed_test_path: str
    repository_facts: ScenarioRepositoryFacts
    development_base_revision: str

    def __post_init__(self) -> None:
        values = (
            self.scenario_id,
            self.language_id,
            self.test_framework,
            self.allowed_test_path,
            self.development_base_revision,
        )
        if any(not value.strip() for value in values):
            raise ValueError("scenario draft request fields must be non-empty")
        if not self.source_requirement_refs or any(not value.strip() for value in self.source_requirement_refs):
            raise ValueError("scenario draft request requires source requirement refs")
        if self.allowed_test_path != self.ticket.test_path:
            raise ValueError("scenario draft path must match the behavior ticket")
        if self.repository_facts.trusted_revision != self.development_base_revision:
            raise ValueError("repository facts must match the development base")


@dataclass(frozen=True)
class ScenarioDraftAttempt:
    attempt_number: int
    work_unit_id: str
    change_id: str | None
    candidate_revision: str | None
    evidence_location: str | None
    status: str
    feedback: str | None = None
    intent: ScenarioIntentResult | None = None
    candidate: ScenarioSourceCandidate | None = None
    static_analysis: ScenarioStaticAnalysis | None = None
    candidate_assessment: ScenarioCandidateAssessment | None = None
    candidate_branch: str | None = None
    candidate_source: str | None = None
    repair_parent_attempt: int | None = None
    repair_base_ref: str | None = None
    repair_base_sha: str | None = None
    repair_mode: str = "fresh_draft"
    selected_worker_id: str | None = None
    worker_provenance: WorkerExecutionProvenance | None = None
    unchanged_evidence: ScenarioCandidateUnchangedEvidence | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("scenario draft attempt number must be positive")
        if not self.work_unit_id.strip() or not self.status.strip():
            raise ValueError("scenario draft attempt fields must be non-empty")
        if self.feedback is not None and not self.feedback.strip():
            raise ValueError("scenario draft feedback must be non-empty when supplied")
        if self.candidate_source is not None and len(self.candidate_source) > MAX_SCENARIO_CANDIDATE_SOURCE_CHARACTERS:
            raise ValueError("candidate source exceeds the scenario test-file limit")

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "intent": None if self.intent is None else self.intent.to_dict(),
            "candidate": None if self.candidate is None else self.candidate.to_dict(),
            "static_analysis": None if self.static_analysis is None else asdict(self.static_analysis),
            "candidate_assessment": None if self.candidate_assessment is None else self.candidate_assessment.to_dict(),
            "worker_provenance": None if self.worker_provenance is None else asdict(self.worker_provenance),
            "unchanged_evidence": None if self.unchanged_evidence is None else self.unchanged_evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioDraftAttempt":
        intent = value.get("intent")
        candidate = value.get("candidate")
        static_analysis = value.get("static_analysis")
        candidate_assessment = value.get("candidate_assessment")
        worker_provenance = value.get("worker_provenance")
        unchanged_evidence = value.get("unchanged_evidence")
        return cls(
            attempt_number=int(value["attempt_number"]),
            work_unit_id=str(value["work_unit_id"]),
            change_id=value.get("change_id"),
            candidate_revision=value.get("candidate_revision"),
            evidence_location=value.get("evidence_location"),
            status=str(value["status"]),
            feedback=value.get("feedback"),
            intent=None if intent is None else ScenarioIntentResult.from_dict(dict(intent)),
            candidate=None if candidate is None else ScenarioSourceCandidate.from_dict(dict(candidate)),
            candidate_assessment=None if candidate_assessment is None else ScenarioCandidateAssessment.from_dict(dict(candidate_assessment)),
            candidate_branch=value.get("candidate_branch"),
            candidate_source=value.get("candidate_source"),
            repair_parent_attempt=value.get("repair_parent_attempt"),
            repair_base_ref=value.get("repair_base_ref"),
            repair_base_sha=value.get("repair_base_sha"),
            repair_mode=str(value.get("repair_mode", "fresh_draft")),
            selected_worker_id=value.get("selected_worker_id"),
            worker_provenance=None if worker_provenance is None else WorkerExecutionProvenance(**dict(worker_provenance)),
            unchanged_evidence=None if unchanged_evidence is None else ScenarioCandidateUnchangedEvidence.from_dict(dict(unchanged_evidence)),
            static_analysis=None if static_analysis is None else ScenarioStaticAnalysis(
                actual_test_identity=str(static_analysis["actual_test_identity"]),
                production_reference_paths=tuple(static_analysis.get("production_reference_paths", ())),
                substitute_definitions=tuple(static_analysis.get("substitute_definitions", ())),
                mocked_behavior_targets=tuple(static_analysis.get("mocked_behavior_targets", ())),
                evasion_markers=tuple(static_analysis.get("evasion_markers", ())),
            ),
        )


@dataclass(frozen=True)
class ScenarioDraftRunState:
    scenario_id: str
    behavior_ref: str
    source_requirement_refs: tuple[str, ...]
    language_id: str
    test_framework: str
    allowed_test_path: str
    development_base_revision: str
    attempts: tuple[ScenarioDraftAttempt, ...] = ()
    approved_microcycle: MicrocycleState | None = None
    status: str = ScenarioDraftStatus.DRAFTING.value
    project_synchronised: bool = False

    def __post_init__(self) -> None:
        values = (
            self.scenario_id,
            self.behavior_ref,
            self.language_id,
            self.test_framework,
            self.allowed_test_path,
            self.development_base_revision,
            self.status,
        )
        if any(not value.strip() for value in values):
            raise ValueError("scenario draft state fields must be non-empty")
        if not self.source_requirement_refs or any(not value.strip() for value in self.source_requirement_refs):
            raise ValueError("scenario draft state requires source requirement refs")
        if self.status not in {item.value for item in ScenarioDraftStatus}:
            raise ValueError("unsupported scenario draft status")
        if self.approved_microcycle is not None and self.status != ScenarioDraftStatus.APPROVED.value:
            raise ValueError("approved scenario state must have approved status")
        if len(self.attempts) > MAX_TESTER_SCENARIO_ATTEMPTS:
            raise ValueError("scenario draft attempt cap exceeded")

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "behavior_ref": self.behavior_ref,
            "source_requirement_refs": list(self.source_requirement_refs),
            "language_id": self.language_id,
            "test_framework": self.test_framework,
            "allowed_test_path": self.allowed_test_path,
            "development_base_revision": self.development_base_revision,
            "attempts": [item.to_dict() for item in self.attempts],
            "approved_microcycle": None if self.approved_microcycle is None else self.approved_microcycle.to_dict(),
            "status": self.status,
            "project_synchronised": self.project_synchronised,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioDraftRunState":
        approved = value.get("approved_microcycle")
        return cls(
            scenario_id=str(value["scenario_id"]),
            behavior_ref=str(value["behavior_ref"]),
            source_requirement_refs=tuple(str(item) for item in value["source_requirement_refs"]),
            language_id=str(value["language_id"]),
            test_framework=str(value["test_framework"]),
            allowed_test_path=str(value["allowed_test_path"]),
            development_base_revision=str(value["development_base_revision"]),
            attempts=tuple(ScenarioDraftAttempt.from_dict(dict(item)) for item in value.get("attempts", ())),
            approved_microcycle=None if approved is None else MicrocycleState.from_dict(dict(approved)),
            status=str(value.get("status", ScenarioDraftStatus.DRAFTING.value)),
            project_synchronised=bool(value.get("project_synchronised", False)),
        )


@dataclass(frozen=True)
class ScenarioDraftOutcome:
    state: ScenarioDraftRunState
    submitted_attempt: bool

    @property
    def approved(self) -> bool:
        return self.state.approved_microcycle is not None
