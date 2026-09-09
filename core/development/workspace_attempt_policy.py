"""ATHBA-owned two-tier workspace model-attempt policy."""
from __future__ import annotations
from dataclasses import asdict, dataclass, replace
from collections.abc import Mapping, Sequence
from enum import Enum

MAX_TIER_SUBMISSIONS = 4

class WorkspaceAttemptTier(str, Enum):
    TIER_ONE = "tier_one"
    TIER_TWO = "tier_two"
    CAPABILITY_BLOCKED = "capability_blocked"

@dataclass(frozen=True)
class WorkspaceSubmissionRecord:
    submission_id: str
    model_originated: bool
    candidate_revision: str | None = None
    evidence_ref: str | None = None

@dataclass(frozen=True)
class WorkspaceAttemptState:
    work_id: str
    tier: WorkspaceAttemptTier = WorkspaceAttemptTier.TIER_ONE
    tier_one_submissions: int = 0
    tier_two_submissions: int = 0
    global_submission_sequence: int = 0
    submissions: tuple[WorkspaceSubmissionRecord, ...] = ()
    repair_parent: str | None = None
    escalation_parent: str | None = None
    base_ref: str | None = None
    base_sha: str | None = None
    allowed_paths: tuple[str, ...] = ()
    active_frontier: str | None = None

    def __post_init__(self) -> None:
        if not self.work_id.strip():
            raise ValueError("workspace attempt state requires a work id")
        if self.tier_one_submissions > MAX_TIER_SUBMISSIONS or self.tier_two_submissions > MAX_TIER_SUBMISSIONS:
            raise ValueError("a workspace tier cannot exceed four submissions")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "WorkspaceAttemptState":
        raw_records = payload.get("submissions", ())
        raw_paths = payload.get("allowed_paths", ())
        if not isinstance(raw_records, Sequence) or not isinstance(raw_paths, Sequence):
            raise ValueError("workspace attempt persistence collections are malformed")
        records = tuple(WorkspaceSubmissionRecord(**dict(item)) for item in raw_records if isinstance(item, Mapping))
        if len(records) != len(raw_records):
            raise ValueError("workspace submission persistence record is malformed")
        return cls(str(payload["work_id"]), WorkspaceAttemptTier(str(payload.get("tier", WorkspaceAttemptTier.TIER_ONE.value))), _integer(payload.get("tier_one_submissions", 0)), _integer(payload.get("tier_two_submissions", 0)), _integer(payload.get("global_submission_sequence", 0)), records, _optional_text(payload.get("repair_parent")), _optional_text(payload.get("escalation_parent")), _optional_text(payload.get("base_ref")), _optional_text(payload.get("base_sha")), tuple(str(item) for item in raw_paths), _optional_text(payload.get("active_frontier")))

class WorkspaceAttemptPolicy:
    """Advances tiers only after four model-originated failures in that tier."""
    def record_model_failure(self, state: WorkspaceAttemptState, record: WorkspaceSubmissionRecord) -> WorkspaceAttemptState:
        if state.tier == WorkspaceAttemptTier.CAPABILITY_BLOCKED:
            return state
        if record.submission_id in {item.submission_id for item in state.submissions}:
            return state
        updated = self._record(state, record)
        if updated.tier == WorkspaceAttemptTier.TIER_ONE and updated.tier_one_submissions == MAX_TIER_SUBMISSIONS:
            return replace(updated, tier=WorkspaceAttemptTier.TIER_TWO, escalation_parent=record.submission_id)
        if updated.tier == WorkspaceAttemptTier.TIER_TWO and updated.tier_two_submissions == MAX_TIER_SUBMISSIONS:
            return replace(updated, tier=WorkspaceAttemptTier.CAPABILITY_BLOCKED)
        return updated

    @staticmethod
    def record_external_blocker(state: WorkspaceAttemptState) -> WorkspaceAttemptState:
        return state

    @staticmethod
    def can_submit(state: WorkspaceAttemptState) -> bool:
        return state.tier != WorkspaceAttemptTier.CAPABILITY_BLOCKED

    @staticmethod
    def _record(state: WorkspaceAttemptState, record: WorkspaceSubmissionRecord) -> WorkspaceAttemptState:
        tier_one = state.tier_one_submissions + (1 if state.tier == WorkspaceAttemptTier.TIER_ONE else 0)
        tier_two = state.tier_two_submissions + (1 if state.tier == WorkspaceAttemptTier.TIER_TWO else 0)
        return replace(state, tier_one_submissions=tier_one, tier_two_submissions=tier_two, global_submission_sequence=state.global_submission_sequence + 1, submissions=(*state.submissions, record), repair_parent=record.candidate_revision or state.repair_parent)


def _optional_text(value: object) -> str | None:
    return str(value) if value is not None else None


def _integer(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("workspace attempt count must be an integer")
    try:
        return int(str(value))
    except ValueError as error:
        raise ValueError("workspace attempt count must be an integer") from error
