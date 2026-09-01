"""Typed, stable transition results for checkpoint-driven strict TDD."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MicrocycleTransitionKind(str, Enum):
    STATE_INITIALISED = "state_initialised"
    PASSING_FRONTIER_OBSERVED = "passing_frontier_observed"
    FRONTIER_RED_ACCEPTED = "frontier_red_accepted"
    DEVELOPER_CANDIDATE_REJECTED = "developer_candidate_rejected"
    DEVELOPER_CANDIDATE_ACCEPTED = "developer_candidate_accepted"
    REGRESSION_CLEAR = "regression_clear"
    ACCUMULATED_REGRESSION = "accumulated_regression"
    REGRESSION_INFRASTRUCTURE_FAILURE = "regression_infrastructure_failure"
    REGRESSION_REPAIR_SUBMITTED = "regression_repair_submitted"
    REGRESSION_REPAIR_CLEARED = "regression_repair_cleared"
    FRONTIER_ADVANCED = "frontier_advanced"
    SCENARIO_COMPLETED = "scenario_completed"
    BEHAVIOR_REVIEW_APPROVED = "behavior_review_approved"
    BEHAVIOR_REVIEW_REPAIR_REQUIRED = "behavior_review_repair_required"
    BEHAVIOR_REPAIR_SUBMITTED = "behavior_repair_submitted"
    BEHAVIOR_REPAIR_REGRESSION_CLEAR = "behavior_repair_regression_clear"
    BEHAVIOR_REPLAN_REQUIRED = "behavior_replan_required"
    BEHAVIOR_COMPLETED = "behavior_completed"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    BLOCKED = "blocked"


class ScenarioTransitionKind(str, Enum):
    DRAFT_ATTEMPTED = "draft_attempted"
    INTENT_APPROVED = "intent_approved"
    REVISION_INITIALISED = "revision_initialised"
    MICROCYCLE_ADVANCED = "microcycle_advanced"
    PROJECT_SYNCHRONISED = "project_synchronised"
    SCENARIO_COMPLETED = "scenario_completed"
    BLOCKED = "blocked"


class FeatureTransitionKind(str, Enum):
    PROJECT_LOADED = "project_loaded"
    PLAN_PERSISTED = "plan_persisted"
    BEHAVIOR_SELECTED = "behavior_selected"
    SCENARIO_ADVANCED = "scenario_advanced"
    BEHAVIOR_RECORDED = "behavior_recorded"
    RECONCILIATION_COMPLETED = "reconciliation_completed"
    FEATURE_COMPLETED = "feature_completed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class TransitionFingerprint:
    """Only stable persisted workflow identity; excludes evidence prose and timestamps."""

    status: str
    behavior_ref: str | None
    scenario_id: str | None
    frontier_index: int | None
    canonical_sha: str | None
    working_sha: str | None
    retry_counts: tuple[int, ...]
    pending_action: str


@dataclass(frozen=True)
class MicrocycleAdvanceRequest:
    request: object


@dataclass(frozen=True)
class MicrocycleAdvanceResult:
    kind: MicrocycleTransitionKind
    prior_status: str
    resulting_status: str
    project_id: str
    behavior_ref: str
    scenario_id: str
    frontier_index: int
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
    fingerprint: TransitionFingerprint
    state: object


@dataclass(frozen=True)
class ScenarioAdvanceRequest:
    request: object


@dataclass(frozen=True)
class ScenarioAdvanceResult:
    kind: ScenarioTransitionKind
    prior_status: str
    resulting_status: str
    behavior_ref: str
    scenario_id: str
    canonical_ref: str | None
    canonical_sha: str | None
    working_ref: str | None
    working_sha: str | None
    evidence_refs: tuple[str, ...]
    external_reasoning_invoked: bool
    rack_ai_invoked: bool
    another_transition_available: bool
    blocker_or_replan_reason: str | None
    fingerprint: TransitionFingerprint
    result: object


@dataclass(frozen=True)
class FeatureAdvanceRequest:
    request: object


@dataclass(frozen=True)
class FeatureAdvanceResult:
    kind: FeatureTransitionKind
    prior_status: str
    resulting_status: str
    project_id: str
    behavior_ref: str | None
    scenario_id: str | None
    canonical_ref: str | None
    canonical_sha: str | None
    working_ref: str | None
    working_sha: str | None
    evidence_refs: tuple[str, ...]
    external_reasoning_invoked: bool
    rack_ai_invoked: bool
    deterministic_regression_invoked: bool
    another_transition_available: bool
    blocker_or_replan_reason: str | None
    fingerprint: TransitionFingerprint
    result: object
