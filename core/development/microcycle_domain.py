"""Language-neutral, persistent domain records for PR23 strict TDD microcycles."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Protocol

MICROCYCLE_SCHEMA_VERSION = 2
MAX_MICROCYCLE_ATTEMPTS = 4


class IntentStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REPAIR_REQUIRED = "repair_required"
    WRONG_BEHAVIOR = "wrong_behavior"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class BoundaryOutcome(str, Enum):
    VALID_MISSING_CAPABILITY_RED = "valid_missing_capability_red"
    VALID_BEHAVIORAL_RED = "valid_behavioral_red"
    GREEN = "green"
    INVALID_TEST_SYNTAX = "invalid_test_syntax"
    FAILURE_BEFORE_FRONTIER = "failure_before_frontier"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"
    UNSUPPORTED_LANGUAGE_BOUNDARY = "unsupported_language_boundary"


class BehaviorReviewVerdict(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REPAIR_REQUIRED = "repair_required"
    REPLAN_REQUIRED = "replan_required"
    PROTOCOL_FAILURE = "protocol_failure"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


class MicrocyclePendingAction(str, Enum):
    OBSERVE_FRONTIER = "observe_frontier"
    SUBMIT_DEVELOPER = "submit_developer"
    VERIFY_DEVELOPER_GREEN = "verify_developer_green"
    RUN_REGRESSION = "run_regression"
    PROMOTE_CANONICAL_BASE = "promote_canonical_base"
    ADVANCE_FRONTIER = "advance_frontier"
    REVIEW_BEHAVIOR = "review_behavior"
    SUBMIT_REGRESSION_REPAIR = "submit_regression_repair"
    VERIFY_REGRESSION_REPAIR = "verify_regression_repair"
    RUN_REPAIR_REGRESSION = "run_repair_regression"
    PROMOTE_REGRESSION_REPAIR = "promote_regression_repair"
    SUBMIT_BEHAVIOR_REPAIR = "submit_behavior_repair"
    VERIFY_BEHAVIOR_REPAIR = "verify_behavior_repair"
    RUN_BEHAVIOR_REPAIR_REGRESSION = "run_behavior_repair_regression"
    PROMOTE_BEHAVIOR_REPAIR = "promote_behavior_repair"
    COMPLETE_BEHAVIOR = "complete_behavior"
    BLOCKED = "blocked"


class MicrocycleMigrationError(Exception):
    """Raised instead of silently treating an old full-test cycle as a microcycle."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value


def _texts(values: tuple[str, ...], label: str) -> None:
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{label} must contain non-empty strings")


def _outcome(value: object) -> str:
    text = _text(value, "boundary outcome")
    if text not in {item.value for item in BoundaryOutcome}:
        raise ValueError(f"unsupported boundary outcome: {text}")
    return text


@dataclass(frozen=True)
class TestScenarioDraft:
    scenario_id: str
    behavior_ref: str
    language_id: str
    source: str
    canonical_test_identity: str
    test_path: str
    scenario_rationale: str = "not yet supplied"
    source_requirement_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texts((self.scenario_id, self.behavior_ref, self.language_id, self.source, self.canonical_test_identity, self.test_path, self.scenario_rationale), "draft fields")
        _texts(self.source_requirement_refs, "draft source requirement refs")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TestScenarioDraft":
        return cls(
            scenario_id=str(value["scenario_id"]),
            behavior_ref=str(value["behavior_ref"]),
            language_id=str(value["language_id"]),
            source=str(value["source"]),
            canonical_test_identity=str(value["canonical_test_identity"]),
            test_path=str(value["test_path"]),
            scenario_rationale=str(value.get("scenario_rationale", "not yet supplied")),
            source_requirement_refs=tuple(str(item) for item in value.get("source_requirement_refs", ())),
        )


@dataclass(frozen=True)
class ScenarioIntentResult:
    scenario_id: str
    status: str
    rationale: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.scenario_id, "scenario id")
        if self.status not in {item.value for item in IntentStatus}:
            raise ValueError("unsupported scenario intent status")
        _text(self.rationale, "intent rationale")
        _texts(self.evidence_refs, "intent evidence")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioIntentResult":
        return cls(str(value["scenario_id"]), str(value["status"]), str(value["rationale"]), tuple(value.get("evidence_refs", ())))


@dataclass(frozen=True)
class ScenarioSourceCandidate:
    """Model-authored source and Rack AI evidence before ATHBA freezes a draft."""

    scenario_id: str
    behavior_ref: str
    language_id: str
    test_path: str
    source: str
    actual_test_identity: str
    candidate_revision: str
    evidence_location: str

    def __post_init__(self) -> None:
        _texts(
            (
                self.scenario_id,
                self.behavior_ref,
                self.language_id,
                self.test_path,
                self.actual_test_identity,
                self.candidate_revision,
                self.evidence_location,
            ),
            "scenario source candidate fields",
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioSourceCandidate":
        return cls(**{key: str(item) for key, item in value.items()})


@dataclass(frozen=True)
class ScenarioStaticAnalysis:
    """Adapter-owned facts about one candidate, before semantic intent review."""

    actual_test_identity: str
    production_reference_paths: tuple[str, ...] = ()
    substitute_definitions: tuple[str, ...] = ()
    mocked_behavior_targets: tuple[str, ...] = ()
    evasion_markers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.actual_test_identity, "static analysis test identity")
        _texts(self.production_reference_paths, "production reference paths")
        _texts(self.substitute_definitions, "substitute definitions")
        _texts(self.mocked_behavior_targets, "mocked behavior targets")
        _texts(self.evasion_markers, "scenario evasion markers")

    def rejection_feedback(self) -> str | None:
        if self.substitute_definitions:
            return "candidate defines a substitute production implementation"
        if self.mocked_behavior_targets:
            return "candidate mocks the behavior under development"
        if self.evasion_markers:
            return "candidate contains a skip, xfail, or missing-capability evasion"
        if not self.production_reference_paths:
            return "candidate does not reference the declared production path"
        return None


@dataclass(frozen=True)
class ScenarioModel:
    scenario_id: str
    language_id: str
    adapter_version: str
    canonical_test_identity: str
    complete_source: str
    test_path: str

    def __post_init__(self) -> None:
        _texts((self.scenario_id, self.language_id, self.adapter_version, self.canonical_test_identity, self.complete_source, self.test_path), "model fields")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioModel":
        return cls(**{key: str(item) for key, item in value.items()})


@dataclass(frozen=True)
class ScenarioFragment:
    """One syntactically complete operation or block; it is never a raw line."""

    fragment_id: str
    scenario_id: str
    kind: str
    source: str
    declared_capability: str
    depends_on: tuple[str, ...] = ()
    source_span: SourceSpan | None = None

    def __post_init__(self) -> None:
        _texts((self.fragment_id, self.scenario_id, self.kind, self.source, self.declared_capability), "fragment fields")
        _texts(self.depends_on, "fragment dependencies")
        if self.fragment_id in self.depends_on:
            raise ValueError("a fragment cannot depend on itself")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioFragment":
        source_span = value.get("source_span")
        return cls(
            str(value["fragment_id"]), str(value["scenario_id"]), str(value["kind"]),
            str(value["source"]), str(value["declared_capability"]),
            tuple(value.get("depends_on", ())),
            SourceSpan.from_dict(dict(source_span)) if source_span is not None else None,
        )


@dataclass(frozen=True)
class ScenarioFrontier:
    scenario_id: str
    index: int
    active_fragment_id: str
    materialised_fragment_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _texts((self.scenario_id, self.active_fragment_id), "frontier fields")
        _texts(self.materialised_fragment_ids, "frontier fragment ids")
        if self.index < 0 or not self.materialised_fragment_ids or self.active_fragment_id != self.materialised_fragment_ids[-1]:
            raise ValueError("frontier must have an ordered active fragment")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioFrontier":
        return cls(str(value["scenario_id"]), int(value["index"]), str(value["active_fragment_id"]), tuple(value["materialised_fragment_ids"]))


@dataclass(frozen=True)
class SourceSpan:
    start_line: int
    end_line: int

    def __post_init__(self) -> None:
        if self.start_line < 1 or self.end_line < self.start_line:
            raise ValueError("source span is invalid")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SourceSpan":
        return cls(int(value["start_line"]), int(value["end_line"]))


@dataclass(frozen=True)
class FragmentSourceSpan:
    fragment_id: str
    span: SourceSpan

    def __post_init__(self) -> None:
        _text(self.fragment_id, "fragment span id")

    def to_dict(self) -> dict[str, object]:
        return {"fragment_id": self.fragment_id, "span": self.span.to_dict()}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FragmentSourceSpan":
        return cls(str(value["fragment_id"]), SourceSpan.from_dict(dict(value["span"])))


@dataclass(frozen=True)
class MaterialisedTestArtifact:
    adapter_id: str
    adapter_version: str
    scenario_id: str
    frontier_index: int
    canonical_test_identity: str
    complete_source: str
    active_fragment_id: str
    fragment_source_spans: tuple[FragmentSourceSpan, ...]
    base_revision: str
    candidate_revision: str | None = None

    def __post_init__(self) -> None:
        _texts((self.adapter_id, self.adapter_version, self.scenario_id, self.canonical_test_identity, self.complete_source, self.active_fragment_id, self.base_revision), "artifact fields")
        ids = tuple(item.fragment_id for item in self.fragment_source_spans)
        if self.frontier_index < 0 or self.active_fragment_id not in ids or len(ids) != len(set(ids)):
            raise ValueError("artifact source-span mapping is invalid")

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "fragment_source_spans": [item.to_dict() for item in self.fragment_source_spans]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MaterialisedTestArtifact":
        return cls(str(value["adapter_id"]), str(value["adapter_version"]), str(value["scenario_id"]), int(value["frontier_index"]), str(value["canonical_test_identity"]), str(value["complete_source"]), str(value["active_fragment_id"]), tuple(FragmentSourceSpan.from_dict(dict(item)) for item in value["fragment_source_spans"]), str(value["base_revision"]), value.get("candidate_revision"))


@dataclass(frozen=True)
class DiagnosticFact:
    name: str
    value: str

    def __post_init__(self) -> None:
        _texts((self.name, self.value), "diagnostic fact")


@dataclass(frozen=True)
class BoundaryDiagnostic:
    kind: str
    message: str
    evidence_refs: tuple[str, ...] = ()
    facts: tuple[DiagnosticFact, ...] = ()

    def __post_init__(self) -> None:
        _texts((self.kind, self.message), "diagnostic fields")
        _texts(self.evidence_refs, "diagnostic evidence")

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "facts": [asdict(item) for item in self.facts]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BoundaryDiagnostic":
        return cls(
            str(value["kind"]), str(value["message"]), tuple(value.get("evidence_refs", ())),
            tuple(DiagnosticFact(str(item["name"]), str(item["value"])) for item in value.get("facts", ())),
        )


@dataclass(frozen=True)
class BoundaryAssessment:
    outcome: str
    active_fragment_id: str
    diagnostic: BoundaryDiagnostic

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", _outcome(self.outcome))
        _text(self.active_fragment_id, "active fragment id")

    def to_dict(self) -> dict[str, object]:
        return {"outcome": self.outcome, "active_fragment_id": self.active_fragment_id, "diagnostic": self.diagnostic.to_dict()}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BoundaryAssessment":
        return cls(str(value["outcome"]), str(value["active_fragment_id"]), BoundaryDiagnostic.from_dict(dict(value["diagnostic"])))


@dataclass(frozen=True)
class RetryCounts:
    developer: int = 0
    regression: int = 0
    frontier_execution: int = 0

    def __post_init__(self) -> None:
        if min(self.developer, self.regression, self.frontier_execution) < 0:
            raise ValueError("retry counts must not be negative")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RetryCounts":
        return cls(**{key: int(item) for key, item in value.items()})


@dataclass(frozen=True)
class FrontierAttemptCounts:
    """Durable retry counters for one unchanged frontier and candidate base."""

    frontier_index: int
    base_revision: str
    executions: int = 0
    developer_attempts: int = 0

    def __post_init__(self) -> None:
        if self.frontier_index < 0:
            raise ValueError("frontier attempt index must not be negative")
        _text(self.base_revision, "frontier attempt base revision")
        if min(self.executions, self.developer_attempts) < 0:
            raise ValueError("frontier attempt counts must not be negative")
        if max(self.executions, self.developer_attempts) > MAX_MICROCYCLE_ATTEMPTS:
            raise ValueError("frontier attempt cap exceeded")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "FrontierAttemptCounts":
        return cls(
            int(value["frontier_index"]),
            str(value["base_revision"]),
            int(value.get("executions", 0)),
            int(value.get("developer_attempts", 0)),
        )


@dataclass(frozen=True)
class DeveloperAttempt:
    attempt_number: int
    frontier_index: int
    base_revision: str
    candidate_revision: str | None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.attempt_number < 1 or self.frontier_index < 0:
            raise ValueError("developer attempt is invalid")
        _text(self.base_revision, "developer attempt base revision")
        _texts(self.evidence_refs, "developer attempt evidence")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DeveloperAttempt":
        return cls(int(value["attempt_number"]), int(value["frontier_index"]), str(value["base_revision"]), value.get("candidate_revision"), tuple(value.get("evidence_refs", ())))


@dataclass(frozen=True)
class RegressionCommandReport:
    """Structured evidence emitted by one deterministic project-runtime command."""

    target: str
    command: tuple[str, ...]
    return_code: int | None
    status: str
    evidence_ref: str

    def __post_init__(self) -> None:
        _texts((self.target, self.status, self.evidence_ref), "regression report fields")
        _texts(self.command, "regression report command")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RegressionCommandReport":
        return cls(
            str(value["target"]),
            tuple(str(item) for item in value["command"]),
            None if value.get("return_code") is None else int(value["return_code"]),
            str(value["status"]),
            str(value["evidence_ref"]),
        )


@dataclass(frozen=True)
class RegressionState:
    status: str
    command: tuple[str, ...]
    evidence_refs: tuple[str, ...] = ()
    reports: tuple[RegressionCommandReport, ...] = ()
    failing_prior_test_nodes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texts((self.status,), "regression status")
        _texts(self.command, "regression command")
        _texts(self.evidence_refs, "regression evidence")
        _texts(self.failing_prior_test_nodes, "failing prior test nodes")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "command": list(self.command),
            "evidence_refs": list(self.evidence_refs),
            "reports": [item.to_dict() for item in self.reports],
            "failing_prior_test_nodes": list(self.failing_prior_test_nodes),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RegressionState":
        return cls(
            str(value["status"]),
            tuple(value["command"]),
            tuple(value.get("evidence_refs", ())),
            tuple(RegressionCommandReport.from_dict(dict(item)) for item in value.get("reports", ())),
            tuple(value.get("failing_prior_test_nodes", ())),
        )


@dataclass(frozen=True)
class BehaviorRepairExecution:
    work_unit_id: str
    candidate_revision: str | None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.work_unit_id, "behavior repair work unit")
        _texts(self.evidence_refs, "behavior repair evidence")


@dataclass(frozen=True)
class BehaviorRepairProgress:
    attempts: int = 0
    current_candidate_revision: str | None = None
    execution: BehaviorRepairExecution | None = None
    regression: RegressionState | None = None

    def __post_init__(self) -> None:
        if self.attempts < 0 or self.attempts > MAX_MICROCYCLE_ATTEMPTS:
            raise ValueError("behavior repair attempt count is invalid")
        if self.current_candidate_revision is not None:
            _text(self.current_candidate_revision, "behavior repair candidate revision")

    def to_dict(self) -> dict[str, object]:
        return {
            "attempts": self.attempts,
            "current_candidate_revision": self.current_candidate_revision,
            "execution": asdict(self.execution) if self.execution is not None else None,
            "regression": self.regression.to_dict() if self.regression is not None else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BehaviorRepairProgress":
        execution = value.get("execution")
        regression = value.get("regression")
        return cls(
            int(value.get("attempts", 0)),
            value.get("current_candidate_revision"),
            BehaviorRepairExecution(
                str(execution["work_unit_id"]),
                execution.get("candidate_revision"),
                tuple(execution.get("evidence_refs", ())),
            ) if execution is not None else None,
            RegressionState.from_dict(dict(regression)) if regression is not None else None,
        )


@dataclass(frozen=True)
class BehaviorReplanState:
    candidate_revision: str
    rationale: str
    findings: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _texts((self.candidate_revision, self.rationale), "behavior replan fields")
        _texts(self.findings, "behavior replan findings")
        _texts(self.evidence_refs, "behavior replan evidence")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BehaviorReplanState":
        return cls(
            str(value["candidate_revision"]),
            str(value["rationale"]),
            tuple(value.get("findings", ())),
            tuple(value.get("evidence_refs", ())),
        )


@dataclass(frozen=True)
class BehaviorReviewProtocolFailure:
    purpose: str
    response_attempts: int
    first_response_digest: str | None
    repair_response_digest: str | None
    parse_error: str | None
    schema_error: str | None
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BehaviorReviewProtocolFailure":
        return cls(str(value["purpose"]), int(value["response_attempts"]), value.get("first_response_digest"), value.get("repair_response_digest"), value.get("parse_error"), value.get("schema_error"), tuple(value.get("evidence_refs", ())))


@dataclass(frozen=True)
class BehaviorReviewState:
    """Persistent decision and distinct bounded post-review repair progress."""

    verdict: str = BehaviorReviewVerdict.PENDING.value
    attempts: int = 0
    evidence_refs: tuple[str, ...] = ()
    next_behavior_ticket: str | None = None
    rationale: str = ""
    findings: tuple[str, ...] = ()
    reviewed_candidate_revision: str | None = None
    repair: BehaviorRepairProgress = BehaviorRepairProgress()
    replan: BehaviorReplanState | None = None
    production_diff: str = ""
    protocol_failure: BehaviorReviewProtocolFailure | None = None

    def __post_init__(self) -> None:
        if self.verdict not in {item.value for item in BehaviorReviewVerdict}:
            raise ValueError("unsupported behavior review verdict")
        if self.attempts < 0:
            raise ValueError("behavior review attempts must not be negative")
        _texts(self.evidence_refs, "behavior review evidence")
        _texts(self.findings, "behavior review findings")
        if self.rationale:
            _text(self.rationale, "behavior review rationale")
        if self.verdict == BehaviorReviewVerdict.REPAIR_REQUIRED.value and not self.findings:
            raise ValueError("behavior repair review requires descriptive findings")
        if self.verdict == BehaviorReviewVerdict.APPROVED.value and self.findings:
            raise ValueError("approved behavior review cannot retain repair findings")
        if self.verdict == BehaviorReviewVerdict.PROTOCOL_FAILURE.value and self.protocol_failure is None:
            raise ValueError("behavior review protocol failure requires evidence")
        if self.verdict != BehaviorReviewVerdict.PROTOCOL_FAILURE.value and self.protocol_failure is not None:
            raise ValueError("semantic behavior review cannot retain protocol failure")
        if self.reviewed_candidate_revision is not None:
            _text(self.reviewed_candidate_revision, "reviewed candidate revision")
        if self.next_behavior_ticket is not None:
            _text(self.next_behavior_ticket, "next behavior ticket")

    def to_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "attempts": self.attempts,
            "evidence_refs": list(self.evidence_refs),
            "next_behavior_ticket": self.next_behavior_ticket,
            "rationale": self.rationale,
            "findings": list(self.findings),
            "reviewed_candidate_revision": self.reviewed_candidate_revision,
            "repair": self.repair.to_dict(),
            "replan": asdict(self.replan) if self.replan is not None else None,
            "production_diff": self.production_diff,
            "protocol_failure": self.protocol_failure.to_dict() if self.protocol_failure is not None else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BehaviorReviewState":
        repair = value.get("repair", {})
        replan = value.get("replan")
        protocol_failure = value.get("protocol_failure")
        return cls(
            str(value.get("verdict", BehaviorReviewVerdict.PENDING.value)),
            int(value.get("attempts", 0)),
            tuple(value.get("evidence_refs", ())),
            value.get("next_behavior_ticket"),
            str(value.get("rationale", "")),
            tuple(value.get("findings", ())),
            value.get("reviewed_candidate_revision"),
            BehaviorRepairProgress.from_dict(dict(repair)),
            BehaviorReplanState.from_dict(dict(replan)) if replan is not None else None,
            str(value.get("production_diff", "")),
            BehaviorReviewProtocolFailure.from_dict(dict(protocol_failure)) if protocol_failure is not None else None,
        )


@dataclass(frozen=True)
class ScenarioCompletion:
    status: str
    completed_revision: str | None = None

    def __post_init__(self) -> None:
        _text(self.status, "completion status")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioCompletion":
        return cls(str(value["status"]), value.get("completed_revision"))


@dataclass(frozen=True)
class MicrocycleState:
    scenario_draft: TestScenarioDraft
    intent: ScenarioIntentResult
    model: ScenarioModel
    fragments: tuple[ScenarioFragment, ...]
    frontier: ScenarioFrontier
    development_base_revision: str
    current_accepted_red_revision: str | None
    retry_counts: RetryCounts
    boundary_evidence: tuple[BoundaryAssessment, ...]
    developer_attempts: tuple[DeveloperAttempt, ...]
    regression: RegressionState
    completion: ScenarioCompletion
    schema_version: int = MICROCYCLE_SCHEMA_VERSION
    candidate_chain_revision: str | None = None
    frontier_attempt_counts: tuple[FrontierAttemptCounts, ...] = ()
    behavior_review: BehaviorReviewState = BehaviorReviewState()
    pending_action: str = MicrocyclePendingAction.OBSERVE_FRONTIER.value

    def __post_init__(self) -> None:
        if self.schema_version != MICROCYCLE_SCHEMA_VERSION:
            raise MicrocycleMigrationError(f"unsupported microcycle schema version: {self.schema_version}")
        if self.pending_action not in {item.value for item in MicrocyclePendingAction}:
            raise ValueError("unsupported microcycle pending action")
        _text(self.development_base_revision, "development base revision")
        _validate_state(self)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scenario_draft": self.scenario_draft.to_dict(),
            "intent": self.intent.to_dict(),
            "model": self.model.to_dict(),
            "fragments": [item.to_dict() for item in self.fragments],
            "frontier": self.frontier.to_dict(),
            "development_base_revision": self.development_base_revision,
            "current_accepted_red_revision": self.current_accepted_red_revision,
            "retry_counts": self.retry_counts.to_dict(),
            "boundary_evidence": [item.to_dict() for item in self.boundary_evidence],
            "developer_attempts": [item.to_dict() for item in self.developer_attempts],
            "regression": self.regression.to_dict(),
            "completion": self.completion.to_dict(),
            "candidate_chain_revision": self.candidate_chain_revision,
            "frontier_attempt_counts": [item.to_dict() for item in self.frontier_attempt_counts],
            "behavior_review": self.behavior_review.to_dict(),
            "pending_action": self.pending_action,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MicrocycleState":
        if "schema_version" not in value:
            raise MicrocycleMigrationError("legacy PR17 state has no microcycle schema version; explicit migration is required")
        return cls(
            TestScenarioDraft.from_dict(dict(value["scenario_draft"])),
            ScenarioIntentResult.from_dict(dict(value["intent"])),
            ScenarioModel.from_dict(dict(value["model"])),
            tuple(ScenarioFragment.from_dict(dict(item)) for item in value["fragments"]),
            ScenarioFrontier.from_dict(dict(value["frontier"])),
            str(value["development_base_revision"]),
            value.get("current_accepted_red_revision"),
            RetryCounts.from_dict(dict(value["retry_counts"])),
            tuple(BoundaryAssessment.from_dict(dict(item)) for item in value.get("boundary_evidence", ())),
            tuple(DeveloperAttempt.from_dict(dict(item)) for item in value.get("developer_attempts", ())),
            RegressionState.from_dict(dict(value["regression"])),
            ScenarioCompletion.from_dict(dict(value["completion"])),
            MICROCYCLE_SCHEMA_VERSION,
            value.get("candidate_chain_revision"),
            tuple(FrontierAttemptCounts.from_dict(dict(item)) for item in value.get("frontier_attempt_counts", ())),
            BehaviorReviewState.from_dict(dict(value.get("behavior_review", {}))),
            str(value.get("pending_action", _legacy_pending_action(value))),
        )


def _legacy_pending_action(value: dict[str, Any]) -> str:
    completion = dict(value.get("completion", {}))
    if completion.get("status") == "scenario_complete":
        return MicrocyclePendingAction.REVIEW_BEHAVIOR.value
    regression = dict(value.get("regression", {}))
    if regression.get("status") == "regression_clear":
        return MicrocyclePendingAction.PROMOTE_CANONICAL_BASE.value
    if regression.get("status") == "accumulated_regression":
        return MicrocyclePendingAction.SUBMIT_REGRESSION_REPAIR.value
    if value.get("current_accepted_red_revision"):
        return MicrocyclePendingAction.SUBMIT_DEVELOPER.value
    return MicrocyclePendingAction.OBSERVE_FRONTIER.value


def _validate_state(state: MicrocycleState) -> None:
    scenario_id = state.scenario_draft.scenario_id
    if state.intent.scenario_id != scenario_id or state.model.scenario_id != scenario_id or state.frontier.scenario_id != scenario_id:
        raise ValueError("microcycle records must identify one scenario")
    if (
        state.model.language_id != state.scenario_draft.language_id
        or state.model.canonical_test_identity != state.scenario_draft.canonical_test_identity
        or state.model.test_path != state.scenario_draft.test_path
        or state.model.complete_source != state.scenario_draft.source
    ):
        raise ValueError("microcycle model must preserve the approved scenario identity")
    if state.completion.status == "behavior_complete" and state.behavior_review.verdict != "approved":
        raise ValueError("behavior completion requires approved behavior review")
    ids = tuple(fragment.fragment_id for fragment in state.fragments)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("fragment ids must be unique")
    positions = {fragment_id: index for index, fragment_id in enumerate(ids)}
    for fragment in state.fragments:
        if fragment.scenario_id != scenario_id:
            raise ValueError("fragment belongs to another scenario")
        for dependency in fragment.depends_on:
            if dependency not in positions or positions[dependency] >= positions[fragment.fragment_id]:
                raise ValueError("fragment dependencies must be earlier and known")
    if state.frontier.index >= len(ids) or state.frontier.materialised_fragment_ids != ids[:state.frontier.index + 1]:
        raise ValueError("frontier must be the ordered fragment prefix")
    if state.candidate_chain_revision is not None:
        _text(state.candidate_chain_revision, "candidate chain revision")
    keys = tuple((item.frontier_index, item.base_revision) for item in state.frontier_attempt_counts)
    if len(keys) != len(set(keys)):
        raise ValueError("frontier attempt counts must be unique per frontier base")


@dataclass(frozen=True)
class LanguageAdapterDescriptor:
    adapter_id: str
    adapter_version: str
    language_id: str

    def __post_init__(self) -> None:
        _texts((self.adapter_id, self.adapter_version, self.language_id), "adapter fields")


@dataclass(frozen=True)
class ScenarioParseRequest:
    draft: TestScenarioDraft


@dataclass(frozen=True)
class SyntaxValidationRequest:
    model: ScenarioModel


@dataclass(frozen=True)
class FragmentationRequest:
    model: ScenarioModel


@dataclass(frozen=True)
class FrontierMaterialisationRequest:
    model: ScenarioModel
    fragments: tuple[ScenarioFragment, ...]
    frontier: ScenarioFrontier
    base_revision: str


@dataclass(frozen=True)
class FrontierExecutionRequest:
    artifact: MaterialisedTestArtifact
    project_root: str
    test_path: str
    production_path: str | None = None


@dataclass(frozen=True)
class BoundaryClassificationRequest:
    diagnostic: BoundaryDiagnostic
    artifact: MaterialisedTestArtifact
    active_fragment: ScenarioFragment
    prior_frontier_status: str | None = None


@dataclass(frozen=True)
class FinalTestMaterialisationRequest:
    model: ScenarioModel
    fragments: tuple[ScenarioFragment, ...]
    base_revision: str


@dataclass(frozen=True)
class RegressionContract:
    command: tuple[str, ...]


@dataclass(frozen=True)
class RegressionContractRequest:
    model: ScenarioModel


class LanguageTestAdapter(Protocol):
    """Protocol guarantee: every materialised frontier is complete source."""

    descriptor: LanguageAdapterDescriptor

    def parse_scenario(self, request: ScenarioParseRequest) -> ScenarioModel: ...
    def validate_scenario_syntax(self, request: SyntaxValidationRequest) -> bool: ...
    def analyse_candidate(self, candidate: ScenarioSourceCandidate, production_path: str) -> ScenarioStaticAnalysis: ...
    def canonicalise_candidate(self, candidate: ScenarioSourceCandidate, planned_identity: str) -> ScenarioSourceCandidate: ...
    def fragment_scenario(self, request: FragmentationRequest) -> tuple[ScenarioFragment, ...]: ...
    def materialise_frontier(self, request: FrontierMaterialisationRequest) -> MaterialisedTestArtifact: ...
    def execute_frontier(self, request: FrontierExecutionRequest) -> BoundaryDiagnostic: ...
    def classify_boundary(self, request: BoundaryClassificationRequest) -> BoundaryAssessment: ...
    def materialise_final_test(self, request: FinalTestMaterialisationRequest) -> MaterialisedTestArtifact: ...
    def regression_contract(self, request: RegressionContractRequest) -> RegressionContract: ...


@dataclass(frozen=True)
class LanguageAdapterCatalog:
    adapters: tuple[LanguageTestAdapter, ...]

    def for_language(self, language_id: str) -> LanguageTestAdapter:
        matches = tuple(adapter for adapter in self.adapters if adapter.descriptor.language_id == language_id)
        if len(matches) != 1:
            raise ValueError(f"unsupported language boundary: {language_id}")
        return matches[0]
