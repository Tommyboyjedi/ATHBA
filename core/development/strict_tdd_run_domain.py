"""Typed durable outer-run records for strict-TDD feature advancement."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any

from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest, StrictTddFeatureResult
from core.development.strict_tdd_transition_provenance import StrictTddCheckpoint
from core.development.strict_tdd_transitions import FeatureAdvanceResult, FeatureTransitionKind, MicrocycleTransitionKind, ProjectTransitionDisposition, ScenarioTransitionKind, StrictTddTransitionPath, TransitionFingerprint
from core.filesystem_policy import validate_filesystem_identifier

RUN_SCHEMA_VERSION = 1


class StrictTddRunMode(str, Enum):
    START = "start"
    RESUME = "resume"


class StrictTddRunStatus(str, Enum):
    READY = "ready"
    RUNNING = "running"
    CHECKPOINTED = "checkpointed"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    STALLED = "stalled"
    TRANSITION_LIMIT_REACHED = "transition_limit_reached"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass(frozen=True)
class StrictTddRunControllerConfig:
    max_application_transitions_per_invocation: int

    def __post_init__(self) -> None:
        if self.max_application_transitions_per_invocation < 1:
            raise ValueError("controller transition limit must be positive")


@dataclass(frozen=True)
class StrictTddRunRequest:
    run_id: str
    project_id: str
    source_requirement: str
    language_id: str
    test_framework: str
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    state_root: str
    evidence_root: str
    mode: StrictTddRunMode
    requested_checkpoint: StrictTddCheckpoint | None
    athba_revision: str
    rack_ai_revision: str
    configuration: StrictTddRunControllerConfig

    def __post_init__(self) -> None:
        validate_filesystem_identifier(self.run_id, "run id")
        validate_filesystem_identifier(self.project_id, "project id")
        validate_filesystem_identifier(self.state_root, "state root")
        validate_filesystem_identifier(self.evidence_root, "evidence root")
        for value, label in ((self.source_requirement, "source requirement"), (self.language_id, "language id"), (self.test_framework, "test framework"), (self.state_root, "state root"), (self.evidence_root, "evidence root"), (self.athba_revision, "ATHBA revision"), (self.rack_ai_revision, "Rack AI revision")):
            _text(value, label)
        _paths(self.production_paths, "production paths")
        _paths(self.test_paths, "test paths")

    @property
    def immutable_identity_hash(self) -> str:
        payload = {"project_id": self.project_id, "source_requirement": self.source_requirement, "language_id": self.language_id, "test_framework": self.test_framework, "production_paths": list(self.production_paths), "test_paths": list(self.test_paths)}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def feature_request(self) -> StrictTddFeatureRequest:
        return StrictTddFeatureRequest(self.project_id, self.source_requirement, self.language_id, self.test_framework, self.production_paths, self.test_paths, "strict-tdd-controller", self.mode.value, None if self.requested_checkpoint is None else self.requested_checkpoint.value, self.evidence_root)


@dataclass(frozen=True)
class StrictTddTransitionReceipt:
    path: StrictTddTransitionPath
    fingerprint: TransitionFingerprint
    feature_kind: FeatureTransitionKind
    project_id: str
    behavior_ref: str | None
    scenario_id: str | None
    canonical_ref: str | None
    canonical_sha: str | None
    working_ref: str | None
    working_sha: str | None
    candidate_revision: str | None
    evidence_refs: tuple[str, ...]
    external_reasoning_invoked: bool
    rack_ai_invoked: bool
    deterministic_regression_invoked: bool
    another_transition_available: bool
    blocker_or_replan_reason: str | None
    final_reconciliation: tuple[dict[str, object], ...]
    occurrence: int
    project_disposition: ProjectTransitionDisposition | None

    def to_dict(self) -> dict[str, object]:
        return {"path": _path_dict(self.path), "fingerprint": _fingerprint_dict(self.fingerprint), "feature_kind": self.feature_kind.value, "project_id": self.project_id, "behavior_ref": self.behavior_ref, "scenario_id": self.scenario_id, "canonical_ref": self.canonical_ref, "canonical_sha": self.canonical_sha, "working_ref": self.working_ref, "working_sha": self.working_sha, "candidate_revision": self.candidate_revision, "evidence_refs": list(self.evidence_refs), "external_reasoning_invoked": self.external_reasoning_invoked, "rack_ai_invoked": self.rack_ai_invoked, "deterministic_regression_invoked": self.deterministic_regression_invoked, "another_transition_available": self.another_transition_available, "blocker_or_replan_reason": self.blocker_or_replan_reason, "final_reconciliation": list(self.final_reconciliation), "occurrence": self.occurrence, "project_disposition": None if self.project_disposition is None else self.project_disposition.value}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StrictTddTransitionReceipt":
        return cls(_path_from_dict(dict(value["path"])), _fingerprint_from_dict(dict(value["fingerprint"])), FeatureTransitionKind(str(value["feature_kind"])), str(value["project_id"]), _optional(value.get("behavior_ref")), _optional(value.get("scenario_id")), _optional(value.get("canonical_ref")), _optional(value.get("canonical_sha")), _optional(value.get("working_ref")), _optional(value.get("working_sha")), _optional(value.get("candidate_revision")), tuple(str(item) for item in value["evidence_refs"]), bool(value["external_reasoning_invoked"]), bool(value["rack_ai_invoked"]), bool(value["deterministic_regression_invoked"]), bool(value["another_transition_available"]), _optional(value.get("blocker_or_replan_reason")), tuple(dict(item) for item in value.get("final_reconciliation", ())), int(value["occurrence"]), None if value.get("project_disposition") is None else ProjectTransitionDisposition(str(value["project_disposition"])))

    def transition(self) -> FeatureAdvanceResult:
        result = StrictTddFeatureResult(self.project_id, "", self.fingerprint.status, self.canonical_ref, self.canonical_sha, self.working_ref, self.working_sha, self.scenario_id, (), self.blocker_or_replan_reason, self.final_reconciliation, self.evidence_refs)
        return FeatureAdvanceResult(self.feature_kind, self.fingerprint.status, self.fingerprint.status, self.project_id, self.behavior_ref, self.scenario_id, self.canonical_ref, self.canonical_sha, self.working_ref, self.working_sha, self.evidence_refs, self.external_reasoning_invoked, self.rack_ai_invoked, self.deterministic_regression_invoked, self.another_transition_available, self.blocker_or_replan_reason, self.fingerprint, result, self.candidate_revision, self.path, self.project_disposition)


class StrictTddTransitionReceiptFactory:
    def create(self, transition: FeatureAdvanceResult, occurrence: int) -> StrictTddTransitionReceipt:
        if transition.transition_path is None:
            raise ValueError("controller requires typed transition provenance")
        if occurrence < 1:
            raise ValueError("transition occurrence must be positive")
        return StrictTddTransitionReceipt(transition.transition_path, transition.fingerprint, transition.kind, transition.project_id, transition.behavior_ref, transition.scenario_id, transition.canonical_ref, transition.canonical_sha, transition.working_ref, transition.working_sha, transition.candidate_revision, transition.evidence_refs, transition.external_reasoning_invoked, transition.rack_ai_invoked, transition.deterministic_regression_invoked, transition.another_transition_available, transition.blocker_or_replan_reason, transition.result.final_reconciliation, occurrence, transition.project_disposition)


@dataclass(frozen=True)
class StrictTddTransitionInFlight:
    occurrence: int

    def __post_init__(self) -> None:
        if self.occurrence < 1:
            raise ValueError("in-flight occurrence must be positive")


@dataclass(frozen=True)
class StrictTddRunState:
    run_id: str
    project_id: str
    immutable_identity_hash: str
    status: StrictTddRunStatus
    total_application_transition_count: int = 0
    current_invocation_count: int = 0
    reached_checkpoints: tuple[StrictTddCheckpoint, ...] = ()
    last_delivered_fingerprint: TransitionFingerprint | None = None
    last_delivered_path: StrictTddTransitionPath | None = None
    last_lifecycle_event_id: str | None = None
    pending_transition_receipt: StrictTddTransitionReceipt | None = None
    transition_in_flight: StrictTddTransitionInFlight | None = None
    reason: str | None = None
    structured_report_path: str | None = None
    markdown_report_path: str | None = None
    schema_version: int = RUN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        validate_filesystem_identifier(self.run_id, "run id")
        validate_filesystem_identifier(self.project_id, "project id")
        _text(self.immutable_identity_hash, "request identity hash")
        if self.schema_version != RUN_SCHEMA_VERSION:
            raise ValueError("unsupported strict TDD run-state schema version")
        if self.total_application_transition_count < 0 or self.current_invocation_count < 0:
            raise ValueError("transition counts must not be negative")
        if len(set(self.reached_checkpoints)) != len(self.reached_checkpoints):
            raise ValueError("reached checkpoints must be unique")
        if self.transition_in_flight is not None and self.pending_transition_receipt is not None:
            raise ValueError("in-flight and pending receipt are mutually exclusive")
        if self.status == StrictTddRunStatus.RECOVERY_REQUIRED and not self.reason:
            raise ValueError("recovery state requires a reason")

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "run_id": self.run_id, "project_id": self.project_id, "immutable_identity_hash": self.immutable_identity_hash, "status": self.status.value, "total_application_transition_count": self.total_application_transition_count, "current_invocation_count": self.current_invocation_count, "reached_checkpoints": [item.value for item in self.reached_checkpoints], "last_delivered_fingerprint": None if self.last_delivered_fingerprint is None else _fingerprint_dict(self.last_delivered_fingerprint), "last_delivered_path": None if self.last_delivered_path is None else _path_dict(self.last_delivered_path), "last_lifecycle_event_id": self.last_lifecycle_event_id, "pending_transition_receipt": None if self.pending_transition_receipt is None else self.pending_transition_receipt.to_dict(), "transition_in_flight": None if self.transition_in_flight is None else {"occurrence": self.transition_in_flight.occurrence}, "reason": self.reason, "structured_report_path": self.structured_report_path, "markdown_report_path": self.markdown_report_path}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StrictTddRunState":
        try:
            fingerprint, path, receipt, marker = value.get("last_delivered_fingerprint"), value.get("last_delivered_path"), value.get("pending_transition_receipt"), value.get("transition_in_flight")
            return cls(str(value["run_id"]), str(value["project_id"]), str(value["immutable_identity_hash"]), StrictTddRunStatus(str(value["status"])), int(value.get("total_application_transition_count", 0)), int(value.get("current_invocation_count", 0)), tuple(StrictTddCheckpoint(str(item)) for item in value.get("reached_checkpoints", ())), None if fingerprint is None else _fingerprint_from_dict(dict(fingerprint)), None if path is None else _path_from_dict(dict(path)), _optional(value.get("last_lifecycle_event_id")), None if receipt is None else StrictTddTransitionReceipt.from_dict(dict(receipt)), None if marker is None else StrictTddTransitionInFlight(int(dict(marker)["occurrence"])), _optional(value.get("reason")), _optional(value.get("structured_report_path")), _optional(value.get("markdown_report_path")), int(value["schema_version"]))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("malformed strict TDD run state") from error


@dataclass(frozen=True)
class StrictTddRunResult:
    run_id: str
    project_id: str
    status: StrictTddRunStatus
    last_transition_path: StrictTddTransitionPath | None
    canonical_ref: str | None
    canonical_sha: str | None
    working_ref: str | None
    working_sha: str | None
    reached_checkpoint: StrictTddCheckpoint | None
    reason: str | None
    last_lifecycle_event_id: str | None
    structured_report_path: str | None
    markdown_report_path: str | None
    final_reconciliation: tuple[dict[str, object], ...]


def _text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _paths(values: tuple[str, ...], label: str) -> None:
    if not values or any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{label} must contain non-empty paths")


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _path_dict(path: StrictTddTransitionPath) -> dict[str, object]:
    return {"feature_kind": path.feature_kind.value, "scenario_kind": None if path.scenario_kind is None else path.scenario_kind.value, "microcycle_kind": None if path.microcycle_kind is None else path.microcycle_kind.value}


def _path_from_dict(value: dict[str, Any]) -> StrictTddTransitionPath:
    scenario, microcycle = value.get("scenario_kind"), value.get("microcycle_kind")
    return StrictTddTransitionPath(FeatureTransitionKind(str(value["feature_kind"])), None if scenario is None else ScenarioTransitionKind(str(scenario)), None if microcycle is None else MicrocycleTransitionKind(str(microcycle)))


def _fingerprint_dict(value: TransitionFingerprint) -> dict[str, object]:
    return {"status": value.status, "behavior_ref": value.behavior_ref, "scenario_id": value.scenario_id, "frontier_index": value.frontier_index, "canonical_sha": value.canonical_sha, "working_sha": value.working_sha, "retry_counts": list(value.retry_counts), "pending_action": value.pending_action}


def _fingerprint_from_dict(value: dict[str, Any]) -> TransitionFingerprint:
    return TransitionFingerprint(str(value["status"]), _optional(value.get("behavior_ref")), _optional(value.get("scenario_id")), None if value.get("frontier_index") is None else int(value["frontier_index"]), _optional(value.get("canonical_sha")), _optional(value.get("working_sha")), tuple(int(item) for item in value["retry_counts"]), str(value["pending_action"]))