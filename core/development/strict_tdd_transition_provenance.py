"""Typed checkpoint, terminal, and lifecycle projection policy for strict TDD."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json

from core.development.strict_tdd_lifecycle_evidence import (
    LifecycleEventDraft,
    StrictTddLifecycleEventKind,
    StrictTddLifecycleRunContext,
    StrictTddLifecycleStatus,
)
from core.development.strict_tdd_transitions import (
    FeatureAdvanceResult,
    FeatureTransitionKind,
    MicrocycleTransitionKind,
    ScenarioTransitionKind,
    StrictTddTransitionPath,
    TransitionFingerprint,
)


class StrictTddCheckpoint(str, Enum):
    RED_FRONTIER_ACCEPTED = "red_frontier_accepted"
    FIRST_REGRESSION_CLEAR = "first_regression_clear"
    SCENARIO_READY_FOR_REVIEW = "scenario_ready_for_review"


@dataclass(frozen=True)
class StrictTddCheckpointRequest:
    path: StrictTddTransitionPath
    previously_reached: frozenset[StrictTddCheckpoint]


class StrictTddCheckpointPolicy:
    """Matches checkpoints only from declared transition kinds."""

    def match(self, request: StrictTddCheckpointRequest) -> StrictTddCheckpoint | None:
        microcycle = request.path.microcycle_kind
        if microcycle == MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED:
            return StrictTddCheckpoint.RED_FRONTIER_ACCEPTED
        if (
            microcycle == MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED
            and StrictTddCheckpoint.FIRST_REGRESSION_CLEAR not in request.previously_reached
        ):
            return StrictTddCheckpoint.FIRST_REGRESSION_CLEAR
        if microcycle == MicrocycleTransitionKind.SCENARIO_COMPLETED:
            return StrictTddCheckpoint.SCENARIO_READY_FOR_REVIEW
        return None


class StrictTddTerminalDisposition(str, Enum):
    CONTINUE = "continue"
    CHECKPOINT = "checkpoint"
    BLOCKED = "blocked"
    COMPLETED = "completed"


@dataclass(frozen=True)
class StrictTddTerminalPolicyRequest:
    transition: FeatureAdvanceResult
    requested_checkpoint: StrictTddCheckpoint | None
    previously_reached: frozenset[StrictTddCheckpoint]


@dataclass(frozen=True)
class StrictTddTerminalDecision:
    disposition: StrictTddTerminalDisposition
    checkpoint: StrictTddCheckpoint | None = None


class StrictTddTerminalPolicy:
    """Chooses a terminal action from typed provenance and explicit state only."""

    def __init__(self, checkpoints: StrictTddCheckpointPolicy | None = None):
        self.checkpoints = checkpoints or StrictTddCheckpointPolicy()

    def decide(self, request: StrictTddTerminalPolicyRequest) -> StrictTddTerminalDecision:
        transition = request.transition
        if transition.kind == FeatureTransitionKind.BLOCKED or transition.blocker_or_replan_reason is not None:
            return StrictTddTerminalDecision(StrictTddTerminalDisposition.BLOCKED)
        if transition.kind == FeatureTransitionKind.FEATURE_COMPLETED:
            return StrictTddTerminalDecision(StrictTddTerminalDisposition.COMPLETED)
        path = _path(transition)
        reached = self.checkpoints.match(StrictTddCheckpointRequest(path, request.previously_reached))
        if request.requested_checkpoint is not None and reached == request.requested_checkpoint:
            return StrictTddTerminalDecision(StrictTddTerminalDisposition.CHECKPOINT, reached)
        if transition.another_transition_available:
            return StrictTddTerminalDecision(StrictTddTerminalDisposition.CONTINUE)
        return StrictTddTerminalDecision(StrictTddTerminalDisposition.CHECKPOINT, reached)


@dataclass(frozen=True)
class StrictTddTransitionProjectionRequest:
    context: StrictTddLifecycleRunContext
    transition: FeatureAdvanceResult
    occurrence: int

    def __post_init__(self) -> None:
        if self.occurrence < 0:
            raise ValueError("projection occurrence must be non-negative")


class StrictTddTransitionEventProjector:
    """Pure projector from a typed transition into one lifecycle event draft."""

    def project(self, request: StrictTddTransitionProjectionRequest) -> tuple[LifecycleEventDraft, ...]:
        transition = request.transition
        path = _path(transition)
        fingerprint = _fingerprint(transition.fingerprint)
        identity = _event_identity(request.context.run_id, path, fingerprint, request.occurrence)
        evidence = transition.evidence_refs or (f"transition:{transition.kind.value}:{fingerprint}",)
        status = _event_status(path)
        draft = LifecycleEventDraft(
            identity,
            _event_kind(path),
            status,
            evidence,
            scenario_id=transition.scenario_id,
            behavior_ref=transition.behavior_ref,
            frontier_index=None if status == StrictTddLifecycleStatus.COMPLETED else transition.fingerprint.frontier_index,
            canonical_ref=transition.canonical_ref,
            canonical_revision=transition.canonical_sha,
            working_ref=transition.working_ref,
            working_revision=transition.working_sha,
            message=_message(path),
            candidate_revision=transition.candidate_revision,
        )
        return (draft,)


def _path(transition: FeatureAdvanceResult) -> StrictTddTransitionPath:
    if transition.transition_path is None:
        raise ValueError("transition projector requires typed transition provenance")
    return transition.transition_path


def _fingerprint(value: TransitionFingerprint) -> str:
    payload = json.dumps(asdict(value), sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


def _event_identity(
    run_id: str,
    path: StrictTddTransitionPath,
    fingerprint: str,
    occurrence: int,
) -> str:
    payload = json.dumps(
        {
            "run_id": run_id,
            "feature": path.feature_kind.value,
            "scenario": path.scenario_kind.value if path.scenario_kind else None,
            "microcycle": path.microcycle_kind.value if path.microcycle_kind else None,
            "fingerprint": fingerprint,
            "occurrence": occurrence,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"transition-{sha256(payload.encode()).hexdigest()}"


def _event_kind(path: StrictTddTransitionPath) -> StrictTddLifecycleEventKind:
    if path.microcycle_kind is not None:
        return _MICROCYCLE_EVENTS[path.microcycle_kind]
    if path.scenario_kind is not None:
        return _SCENARIO_EVENTS[path.scenario_kind]
    return _FEATURE_EVENTS[path.feature_kind]


def _event_status(path: StrictTddTransitionPath) -> StrictTddLifecycleStatus:
    if path.feature_kind == FeatureTransitionKind.BLOCKED:
        return StrictTddLifecycleStatus.BLOCKED
    if path.feature_kind == FeatureTransitionKind.FEATURE_COMPLETED:
        return StrictTddLifecycleStatus.COMPLETED
    if path.microcycle_kind == MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED:
        return StrictTddLifecycleStatus.ACCEPTED
    if path.microcycle_kind in {MicrocycleTransitionKind.BLOCKED, MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED}:
        return StrictTddLifecycleStatus.BLOCKED
    return StrictTddLifecycleStatus.COMPLETED


def _message(path: StrictTddTransitionPath) -> str:
    values = [path.feature_kind.value]
    if path.scenario_kind is not None:
        values.append(path.scenario_kind.value)
    if path.microcycle_kind is not None:
        values.append(path.microcycle_kind.value)
    return "typed transition: " + " / ".join(values)


_FEATURE_EVENTS = {
    FeatureTransitionKind.PROJECT_LOADED: StrictTddLifecycleEventKind.PROJECT_LOADED,
    FeatureTransitionKind.CONTRACT_PERSISTED: StrictTddLifecycleEventKind.BEHAVIOR_CONTRACT_COMPLETED,
    FeatureTransitionKind.GATEKEEPER_PERSISTED: StrictTddLifecycleEventKind.GATEKEEPER_COMPLETED,
    FeatureTransitionKind.BEHAVIOR_SELECTED: StrictTddLifecycleEventKind.BEHAVIOR_SELECTED,
    FeatureTransitionKind.SCENARIO_ADVANCED: StrictTddLifecycleEventKind.SCENARIO_DRAFTING_COMPLETED,
    FeatureTransitionKind.BEHAVIOR_RECORDED: StrictTddLifecycleEventKind.BEHAVIOR_COMPLETED,
    FeatureTransitionKind.RECONCILIATION_COMPLETED: StrictTddLifecycleEventKind.RECONCILIATION_COMPLETED,
    FeatureTransitionKind.FEATURE_COMPLETED: StrictTddLifecycleEventKind.RUN_COMPLETED,
    FeatureTransitionKind.BLOCKED: StrictTddLifecycleEventKind.RUN_BLOCKED,
}

_SCENARIO_EVENTS = {
    ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED: StrictTddLifecycleEventKind.SCENARIO_DRAFTING_COMPLETED,
    ScenarioTransitionKind.INTENT_APPROVED: StrictTddLifecycleEventKind.SCENARIO_INTENT_COMPLETED,
    ScenarioTransitionKind.INTENT_REPAIR_REQUIRED: StrictTddLifecycleEventKind.SCENARIO_INTENT_COMPLETED,
    ScenarioTransitionKind.REVISION_INITIALISED: StrictTddLifecycleEventKind.WORKING_REF_CREATED,
    ScenarioTransitionKind.MICROCYCLE_ADVANCED: StrictTddLifecycleEventKind.FRONTIER_MATERIALISED,
    ScenarioTransitionKind.PROJECT_SYNCHRONISED: StrictTddLifecycleEventKind.SCENARIO_COMPLETED,
    ScenarioTransitionKind.SCENARIO_COMPLETED: StrictTddLifecycleEventKind.SCENARIO_COMPLETED,
    ScenarioTransitionKind.BLOCKED: StrictTddLifecycleEventKind.RUN_BLOCKED,
}

_MICROCYCLE_EVENTS = {
    MicrocycleTransitionKind.STATE_INITIALISED: StrictTddLifecycleEventKind.WORKING_REF_CREATED,
    MicrocycleTransitionKind.PASSING_FRONTIER_OBSERVED: StrictTddLifecycleEventKind.FRONTIER_MATERIALISED,
    MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED: StrictTddLifecycleEventKind.FRONTIER_RED_ACCEPTED,
    MicrocycleTransitionKind.DEVELOPER_CANDIDATE_REJECTED: StrictTddLifecycleEventKind.DEVELOPER_COMPLETED,
    MicrocycleTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED: StrictTddLifecycleEventKind.DEVELOPER_COMPLETED,
    MicrocycleTransitionKind.GREEN_VERIFIED: StrictTddLifecycleEventKind.DEVELOPER_COMPLETED,
    MicrocycleTransitionKind.REGRESSION_CLEAR: StrictTddLifecycleEventKind.REGRESSION_COMPLETED,
    MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED: StrictTddLifecycleEventKind.CANONICAL_BASE_PROMOTED,
    MicrocycleTransitionKind.ACCUMULATED_REGRESSION: StrictTddLifecycleEventKind.REGRESSION_COMPLETED,
    MicrocycleTransitionKind.REGRESSION_INFRASTRUCTURE_FAILURE: StrictTddLifecycleEventKind.RUN_BLOCKED,
    MicrocycleTransitionKind.REGRESSION_REPAIR_SUBMITTED: StrictTddLifecycleEventKind.DEVELOPER_STARTED,
    MicrocycleTransitionKind.REGRESSION_REPAIR_VERIFIED: StrictTddLifecycleEventKind.DEVELOPER_COMPLETED,
    MicrocycleTransitionKind.REGRESSION_REPAIR_CLEARED: StrictTddLifecycleEventKind.REGRESSION_COMPLETED,
    MicrocycleTransitionKind.FRONTIER_ADVANCED: StrictTddLifecycleEventKind.FRONTIER_ADVANCED,
    MicrocycleTransitionKind.SCENARIO_COMPLETED: StrictTddLifecycleEventKind.SCENARIO_COMPLETED,
    MicrocycleTransitionKind.BEHAVIOR_REVIEW_APPROVED: StrictTddLifecycleEventKind.BEHAVIOR_REVIEW_COMPLETED,
    MicrocycleTransitionKind.BEHAVIOR_REVIEW_REPAIR_REQUIRED: StrictTddLifecycleEventKind.BEHAVIOR_REVIEW_COMPLETED,
    MicrocycleTransitionKind.BEHAVIOR_REPAIR_SUBMITTED: StrictTddLifecycleEventKind.BEHAVIOR_REPAIR_STARTED,
    MicrocycleTransitionKind.BEHAVIOR_REPAIR_VERIFIED: StrictTddLifecycleEventKind.BEHAVIOR_REPAIR_COMPLETED,
    MicrocycleTransitionKind.BEHAVIOR_REPAIR_REGRESSION_CLEAR: StrictTddLifecycleEventKind.REGRESSION_COMPLETED,
    MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED: StrictTddLifecycleEventKind.RUN_BLOCKED,
    MicrocycleTransitionKind.BEHAVIOR_COMPLETED: StrictTddLifecycleEventKind.BEHAVIOR_COMPLETED,
    MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED: StrictTddLifecycleEventKind.RUN_BLOCKED,
    MicrocycleTransitionKind.BLOCKED: StrictTddLifecycleEventKind.RUN_BLOCKED,
}
