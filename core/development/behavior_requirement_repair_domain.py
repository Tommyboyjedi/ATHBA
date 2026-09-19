"""Typed, bounded semantic repair evidence for one logical behavior."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.development.behavior_contract_domain import BehaviorContractRequirement
from core.development.specification_domain import SourceRequirementClause
from core.development.scenario_drafting_domain import MAX_TESTER_SCENARIO_ATTEMPTS


class BehaviorRepairPhase(str, Enum):
    REQUIRED = "behavior_repair_required"
    STARTED = "behavior_repair_started"
    RECEIVED = "behavior_repair_received"
    APPLIED = "behavior_repair_applied"
    FAILED = "behavior_repair_failed"


class BehaviorRepairBlocker(str, Enum):
    INTERRUPTED = "behavior_repair_interrupted"
    PROTOCOL_FAILURE = "behavior_repair_protocol_failure"
    PROVIDER_FAILURE = "behavior_repair_provider_failure"
    NO_PROGRESS = "behavior_repair_no_progress"
    INCOMPATIBLE = "behavior_repair_incompatible"


@dataclass(frozen=True)
class BehaviorRepairFeedback:
    attempt_number: int
    rationale: str

    def __post_init__(self) -> None:
        if (type(self.attempt_number) is not int
                or not 1 <= self.attempt_number <= MAX_TESTER_SCENARIO_ATTEMPTS
                or not isinstance(self.rationale, str) or not self.rationale.strip()):
            raise ValueError("repair feedback requires a bounded attempt and exact non-empty rationale")

    def to_dict(self) -> dict[str, Any]:
        return {"attempt_number": self.attempt_number, "status": "wrong_behavior", "rationale": self.rationale}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BehaviorRepairFeedback:
        if value["status"] != "wrong_behavior":
            raise ValueError("repair feedback must be a wrong_behavior review")
        return cls(value["attempt_number"], value["rationale"])


@dataclass(frozen=True)
class BehaviorRepairRequest:
    project_id: str
    original: BehaviorContractRequirement
    source_clauses: tuple[SourceRequirementClause, ...]
    feedback: tuple[BehaviorRepairFeedback, ...]
    scenario_id: str
    canonical_ref: str
    canonical_revision: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, str) or not value.strip() for value in (
                self.project_id, self.scenario_id, self.canonical_ref, self.canonical_revision)):
            raise ValueError("repair request requires trusted routing identity")
        if tuple(item.ref for item in self.source_clauses) != tuple(self.original.source_refs):
            raise ValueError("repair source clauses must exactly resolve the behavior refs in order")
        numbers = tuple(item.attempt_number for item in self.feedback)
        if not numbers or numbers != tuple(sorted(set(numbers))):
            raise ValueError("repair feedback requires unique reviews in stable attempt order")

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id, "original": self.original.to_dict(),
            "source_clauses": [item.to_dict() for item in self.source_clauses],
            "feedback": [item.to_dict() for item in self.feedback],
            "scenario_id": self.scenario_id, "canonical_ref": self.canonical_ref,
            "canonical_revision": self.canonical_revision,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BehaviorRepairRequest:
        return cls(
            value["project_id"], BehaviorContractRequirement.from_dict(value["original"]),
            tuple(SourceRequirementClause.from_dict(item) for item in value["source_clauses"]),
            tuple(BehaviorRepairFeedback.from_dict(item) for item in value["feedback"]),
            value["scenario_id"], value["canonical_ref"], value["canonical_revision"],
        )


@dataclass(frozen=True)
class BehaviorRepairRecord:
    request: BehaviorRepairRequest
    phase: BehaviorRepairPhase = BehaviorRepairPhase.REQUIRED
    raw_response: str | None = None
    repaired: BehaviorContractRequirement | None = None
    rationale: str | None = None
    blocker: BehaviorRepairBlocker | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(), "phase": self.phase.value,
            "raw_response": self.raw_response,
            "repaired": None if self.repaired is None else self.repaired.to_dict(),
            "rationale": self.rationale,
            "blocker": None if self.blocker is None else self.blocker.value, "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BehaviorRepairRecord:
        return cls(
            BehaviorRepairRequest.from_dict(value["request"]), BehaviorRepairPhase(value["phase"]),
            value["raw_response"],
            None if value["repaired"] is None else BehaviorContractRequirement.from_dict(value["repaired"]),
            value["rationale"],
            None if value["blocker"] is None else BehaviorRepairBlocker(value["blocker"]), value["detail"],
        )


@dataclass(frozen=True)
class BehaviorRepairFailure(Exception):
    kind: BehaviorRepairBlocker
    detail: str
