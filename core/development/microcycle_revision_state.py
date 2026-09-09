"""Typed durable revision state for one strict-TDD microcycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RevisionLifecycleStatus(str, Enum):
    ACTIVE = "active"
    BEHAVIOR_COMPLETE = "behavior_complete"


class RevisionTransitionKind(str, Enum):
    INITIALISED = "initialised"
    FRONTIER_ACCEPTED = "frontier_accepted"
    DEVELOPER_CANDIDATE_ACCEPTED = "developer_candidate_accepted"
    REGRESSION_REPAIR_ACCEPTED = "regression_repair_accepted"
    REGRESSION_CLEAR = "regression_clear"
    BEHAVIOR_COMPLETED = "behavior_completed"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value


def _texts(values: tuple[str, ...], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")


@dataclass(frozen=True)
class MicrocycleRevisionState:
    scenario_id: str
    canonical_ref: str
    canonical_development_base: str
    working_ref: str
    working_revision: str
    status: str
    last_transition: str
    last_evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.scenario_id, "scenario id"),
            (self.canonical_ref, "canonical ref"),
            (self.canonical_development_base, "canonical development base"),
            (self.working_ref, "working ref"),
            (self.working_revision, "working revision"),
        ):
            _text(value, label)
        if self.status not in {item.value for item in RevisionLifecycleStatus}:
            raise ValueError("unsupported revision lifecycle status")
        if self.last_transition not in {item.value for item in RevisionTransitionKind}:
            raise ValueError("unsupported revision transition")
        _texts(self.last_evidence_refs, "revision evidence")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MicrocycleRevisionState":
        return cls(
            str(payload["scenario_id"]), str(payload["canonical_ref"]),
            str(payload["canonical_development_base"]), str(payload["working_ref"]),
            str(payload["working_revision"]), str(payload["status"]),
            str(payload["last_transition"]),
            tuple(str(item) for item in payload.get("last_evidence_refs", ())),
        )


@dataclass(frozen=True)
class RevisionInitialisationRequest:
    scenario_id: str
    canonical_ref: str
    canonical_development_base: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RevisionTransitionRequest:
    expected_current_state: MicrocycleRevisionState
    candidate_revision: str
    transition: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.candidate_revision, "candidate revision")
        if self.transition not in {
            RevisionTransitionKind.FRONTIER_ACCEPTED.value,
            RevisionTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED.value,
            RevisionTransitionKind.REGRESSION_REPAIR_ACCEPTED.value,
            RevisionTransitionKind.REGRESSION_CLEAR.value,
        }:
            raise ValueError("unsupported revision transition request")
        _texts(self.evidence_refs, "transition evidence")


@dataclass(frozen=True)
class RevisionTransitionResult:
    prior_state: MicrocycleRevisionState
    resulting_state: MicrocycleRevisionState
    status: str


@dataclass(frozen=True)
class RevisionRecoveryRequest:
    scenario_id: str


@dataclass(frozen=True)
class RevisionCompletionRequest:
    expected_current_state: MicrocycleRevisionState
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RevisionBindingRequest:
    scenario_id: str
    repository_id: str
    registered_root: str
    environment_resources: tuple[str, ...] = ()