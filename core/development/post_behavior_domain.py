"""Durable values for the narrow PR30 post-behavior lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re

from core.development.post_behavior_assessment import NamingDecision, RefactorDecision
from core.development.reconciliation_progress import ChecklistItemProgress
from core.development.workspace_attempt_policy import WorkspaceAttemptState

MAX_PROMOTED_REFACTOR_PASSES = 4
POST_BEHAVIOR_SCHEMA = "post-behavior/v1"


class PostBehaviorStatus(str, Enum):
    BEHAVIOR_GATEKEEPER_ACCEPTED = "BEHAVIOR_GATEKEEPER_ACCEPTED"
    NAMING_ASSESSMENT_PENDING = "NAMING_ASSESSMENT_PENDING"
    NAMING_RENAME_PENDING = "NAMING_RENAME_PENDING"
    NAMING_VALIDATION_PENDING = "NAMING_VALIDATION_PENDING"
    NAMING_COMPLETE = "NAMING_COMPLETE"
    REFACTOR_ASSESSMENT_PENDING = "REFACTOR_ASSESSMENT_PENDING"
    REFACTOR_CHANGE_PENDING = "REFACTOR_CHANGE_PENDING"
    REFACTOR_VALIDATION_PENDING = "REFACTOR_VALIDATION_PENDING"
    REFACTOR_COMPLETE = "REFACTOR_COMPLETE"
    POST_BEHAVIOR_COMPLETE = "POST_BEHAVIOR_COMPLETE"
    BLOCKED = "BLOCKED"


class PostBehaviorPhase(str, Enum):
    NAMING = "naming"
    REFACTORING = "refactoring"


class PostBehaviorCall(str, Enum):
    NONE = ""
    NAMING_ASSESSOR = "naming_assessor"
    REFACTOR_ASSESSOR = "refactor_assessor"
    MUTATION = "mutation"
    TESTS = "tests"
    GATEKEEPER = "gatekeeper"
    PROMOTION = "promotion"


class PostBehaviorOutcome(str, Enum):
    PENDING = "pending"
    NO_CHANGE = "no_change"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    BOUNDED_STOP = "bounded_stop"


class PostBehaviorReason(str, Enum):
    NAMING_NO_CHANGE = "naming_no_change"
    REFACTOR_NO_CHANGE = "refactor_no_change"
    REFACTOR_LIMIT_REACHED = "refactor_limit_reached"
    REPEATED_REFACTOR_OBJECTIVE = "repeated_refactor_objective"
    REPEATED_RENAME = "repeated_rename"
    CANDIDATE_REJECTED = "candidate_rejected"
    TESTS_FAILED = "accepted_tests_failed"
    GATEKEEPER_FAILED = "specification_gatekeeper_failed"
    INTERRUPTED_CALL = "post_behavior_interrupted_call"
    HUMAN_INTERVENTION = "human_intervention_required"


@dataclass(frozen=True)
class ValidationEvidence:
    revision: str
    passed: bool
    evidence_refs: tuple[str, ...]
    diagnostic: str = ""

    def __post_init__(self) -> None:
        _revision(self.revision)
        if type(self.passed) is not bool or not self.evidence_refs or any(not ref for ref in self.evidence_refs):
            raise ValueError("validation requires a boolean result and retained evidence")


@dataclass(frozen=True)
class PostBehaviorEntry:
    delivery_id: str
    trusted_entry_revision: str
    behaviorally_accepted_revision: str
    production_paths: tuple[str, ...]
    behavioral_authority_digest: str
    gatekeeper_evidence: ValidationEvidence

    def __post_init__(self) -> None:
        _revision(self.trusted_entry_revision)
        _revision(self.behaviorally_accepted_revision)
        if not self.delivery_id or not self.behavioral_authority_digest or not self.production_paths:
            raise ValueError("post-behavior entry requires delivery, authority and production identities")
        if any(not path or path.startswith("/") or ".." in path.split("/") for path in self.production_paths):
            raise ValueError("focused production paths must stay within the repository")
        if not self.gatekeeper_evidence.passed or self.gatekeeper_evidence.revision != self.behaviorally_accepted_revision:
            raise ValueError("post-behavior entry requires final Gatekeeper approval of the exact behavioral SHA")


@dataclass(frozen=True)
class PostBehaviorAssessment:
    decision: NamingDecision | RefactorDecision
    slice_identity: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.slice_identity:
            raise ValueError("assessment requires the focused current production slice identity")


@dataclass(frozen=True)
class ChangeCandidate:
    revision: str | None
    evidence_refs: tuple[str, ...]
    success: bool = True
    diagnostic: str = ""
    model_originated: bool = True

    def __post_init__(self) -> None:
        if self.revision is not None:
            _revision(self.revision)
        if type(self.success) is not bool or not self.evidence_refs:
            raise ValueError("candidate requires a boolean result and execution evidence")
        if self.success and self.revision is None:
            raise ValueError("successful execution requires an exact candidate revision")


@dataclass(frozen=True)
class PostBehaviorPass:
    phase: PostBehaviorPhase
    number: int
    base_revision: str
    assessment: PostBehaviorAssessment | None = None
    submission_id: str | None = None
    candidate: ChangeCandidate | None = None
    tests: ValidationEvidence | None = None
    gatekeeper: ValidationEvidence | None = None
    reconciliation_progress: tuple[ChecklistItemProgress, ...] = ()
    outcome: PostBehaviorOutcome = PostBehaviorOutcome.PENDING
    promotion_evidence: tuple[str, ...] = ()
    stop_reason: PostBehaviorReason | None = None

    def __post_init__(self) -> None:
        _revision(self.base_revision)
        if type(self.number) is not int or self.number < 1:
            raise ValueError("assessor passes begin at one")
        if self.assessment is not None:
            expected = NamingDecision if self.phase == PostBehaviorPhase.NAMING else RefactorDecision
            if not isinstance(self.assessment.decision, expected):
                raise ValueError("assessor decision does not belong to the persisted phase")
        if self.submission_id is not None and not _change_requested(self.assessment):
            raise ValueError("execution requires one affirmative assessor decision")
        if self.candidate is not None and (self.assessment is None or self.submission_id is None):
            raise ValueError("candidate requires a persisted assessor decision and submission")
        for evidence in (self.tests, self.gatekeeper):
            if evidence is not None and (self.candidate is None or evidence.revision != self.candidate.revision):
                raise ValueError("validation evidence does not belong to the candidate")
        if self.gatekeeper is not None and (self.tests is None or not self.tests.passed):
            raise ValueError("Gatekeeper validation requires passing accepted tests")
        if self.outcome == PostBehaviorOutcome.NO_CHANGE:
            if self.assessment is None or _change_requested(self.assessment) or self.candidate is not None:
                raise ValueError("no-change completion requires an explicit assessor NO")
        if self.outcome == PostBehaviorOutcome.PROMOTED:
            if (self.candidate is None or not self.candidate.success or self.tests is None
                    or not self.tests.passed or self.gatekeeper is None or not self.gatekeeper.passed
                    or not self.promotion_evidence):
                raise ValueError("promotion requires candidate, tests and Gatekeeper acceptance evidence")


@dataclass(frozen=True)
class PostBehaviorPolicy:
    max_promoted_refactor_passes: int = MAX_PROMOTED_REFACTOR_PASSES

    def __post_init__(self) -> None:
        if (type(self.max_promoted_refactor_passes) is not int
                or not 1 <= self.max_promoted_refactor_passes <= MAX_PROMOTED_REFACTOR_PASSES):
            raise ValueError("post-behavior refactoring is bounded by at most four promoted passes")


@dataclass(frozen=True)
class PostBehaviorState:
    entry: PostBehaviorEntry
    current_post_behavior_revision: str
    status: PostBehaviorStatus = PostBehaviorStatus.BEHAVIOR_GATEKEEPER_ACCEPTED
    active_pass: PostBehaviorPass | None = None
    passes: tuple[PostBehaviorPass, ...] = ()
    refactor_promoted_passes: int = 0
    pending_call: PostBehaviorCall = PostBehaviorCall.NONE
    terminal_reason: PostBehaviorReason | None = None
    diagnostic: str = ""
    generation: int = 0
    policy: PostBehaviorPolicy = field(default_factory=PostBehaviorPolicy)
    attempt_state: WorkspaceAttemptState | None = None

    def __post_init__(self) -> None:
        _validate_state(self)

    @property
    def behaviorally_accepted_revision(self) -> str:
        return self.entry.behaviorally_accepted_revision

    @property
    def delivery_id(self) -> str:
        return self.entry.delivery_id

    @property
    def terminal(self) -> bool:
        return self.status in {PostBehaviorStatus.POST_BEHAVIOR_COMPLETE, PostBehaviorStatus.BLOCKED}


def _revision(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ValueError("post-behavior revisions must be exact Git SHAs")


def _validate_state(state: PostBehaviorState) -> None:
    if type(state.generation) is not int or type(state.refactor_promoted_passes) is not int:
        raise ValueError("post-behavior progress counts must be integers")
    expected = state.entry.behaviorally_accepted_revision
    promoted = 0
    naming_complete = False
    for number, item in enumerate(state.passes, start=1):
        if item.phase == PostBehaviorPhase.REFACTORING and not naming_complete:
            raise ValueError("refactoring cannot precede naming NO")
        if item.phase == PostBehaviorPhase.NAMING and naming_complete:
            raise ValueError("naming cannot restart after naming NO")
        naming_complete |= item.phase == PostBehaviorPhase.NAMING and item.outcome == PostBehaviorOutcome.NO_CHANGE
        if item.number != number or item.base_revision != expected or item.outcome == PostBehaviorOutcome.PENDING:
            raise ValueError("post-behavior history does not form an accepted revision chain")
        if item.outcome == PostBehaviorOutcome.PROMOTED:
            assert item.candidate is not None and item.candidate.revision is not None
            expected = item.candidate.revision
            promoted += item.phase == PostBehaviorPhase.REFACTORING
    if expected != state.current_post_behavior_revision or promoted != state.refactor_promoted_passes:
        raise ValueError("post-behavior trusted revision or promoted-pass count differs from evidence")
    if promoted > state.policy.max_promoted_refactor_passes or state.generation < 0:
        raise ValueError("post-behavior state exceeds its deterministic bounds")
    if state.active_pass is not None:
        if state.active_pass.base_revision != expected or state.active_pass.number != len(state.passes) + 1:
            raise ValueError("pending work must use the current accepted revision")
        if state.active_pass.outcome != PostBehaviorOutcome.PENDING:
            raise ValueError("completed work must be retained in history")
    if state.pending_call != PostBehaviorCall.NONE and state.active_pass is None:
        raise ValueError("in-flight call requires a durable active pass")
    if state.status == PostBehaviorStatus.BLOCKED and state.terminal_reason is None:
        raise ValueError("blocked post-behavior state requires a recorded reason")

    _validate_phase(state, naming_complete)


def _change_requested(assessment: PostBehaviorAssessment | None) -> bool:
    if assessment is None:
        return False
    decision = assessment.decision
    return decision.rename is not None if isinstance(decision, NamingDecision) else decision.opportunity is not None


def _validate_phase(state: PostBehaviorState, naming_complete: bool) -> None:
    refactor_statuses = {
        PostBehaviorStatus.REFACTOR_ASSESSMENT_PENDING, PostBehaviorStatus.REFACTOR_CHANGE_PENDING,
        PostBehaviorStatus.REFACTOR_VALIDATION_PENDING, PostBehaviorStatus.REFACTOR_COMPLETE,
        PostBehaviorStatus.POST_BEHAVIOR_COMPLETE,
    }
    if state.status in refactor_statuses and not naming_complete:
        raise ValueError("refactoring state requires completed naming reconciliation")
    if state.active_pass is not None:
        refactoring = state.active_pass.phase == PostBehaviorPhase.REFACTORING
        if refactoring and not naming_complete:
            raise ValueError("pending refactoring cannot precede naming NO")
        if state.status != PostBehaviorStatus.BLOCKED and refactoring != (state.status in refactor_statuses):
            raise ValueError("pending pass phase differs from lifecycle status")
    mutation_statuses = {
        PostBehaviorStatus.NAMING_RENAME_PENDING, PostBehaviorStatus.REFACTOR_CHANGE_PENDING,
        PostBehaviorStatus.NAMING_VALIDATION_PENDING, PostBehaviorStatus.REFACTOR_VALIDATION_PENDING,
    }
    if state.status in mutation_statuses and (
            state.active_pass is None or not _change_requested(state.active_pass.assessment)):
        raise ValueError("change and validation states require an affirmative durable decision")
    if state.status == PostBehaviorStatus.NAMING_COMPLETE and not naming_complete:
        raise ValueError("naming completion requires naming NO")
    if state.status in {PostBehaviorStatus.REFACTOR_COMPLETE, PostBehaviorStatus.POST_BEHAVIOR_COMPLETE}:
        if (not state.passes or state.passes[-1].phase != PostBehaviorPhase.REFACTORING
                or state.passes[-1].outcome not in {PostBehaviorOutcome.NO_CHANGE, PostBehaviorOutcome.BOUNDED_STOP}
                or state.terminal_reason != state.passes[-1].stop_reason or state.active_pass is not None):
            raise ValueError("post-behavior completion requires an evidenced refactor stop")
