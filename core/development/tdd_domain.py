"""TDD phase and behavior state records."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.development.tdd_progression_validation import (
    enum_value,
    require_text,
    validate_commands,
)
from core.development.tdd_progression_values import TddPhase


@dataclass(frozen=True)
class TddBehavior:
    id: str
    project_id: str
    parent_ticket_id: str
    description: str
    test_name: str
    test_path: str
    production_path: str
    red_objective: str
    green_objective: str
    red_acceptance_commands: list[list[str]]
    green_acceptance_commands: list[list[str]]

    def __post_init__(self) -> None:
        require_text(self.id, "behavior id")
        require_text(self.project_id, "project id")
        require_text(self.parent_ticket_id, "parent ticket id")
        require_text(self.description, "behavior description")
        require_text(self.test_name, "test name")
        require_text(self.test_path, "test path")
        require_text(self.production_path, "production path")
        require_text(self.red_objective, "red objective")
        require_text(self.green_objective, "green objective")
        validate_commands(self.red_acceptance_commands, "red acceptance commands")
        validate_commands(self.green_acceptance_commands, "green acceptance commands")


@dataclass(frozen=True)
class TddPhaseState:
    phase: str
    work_unit_id: str
    base_sha: str | None = None
    status: str = "pending"
    accepted_revision: str | None = None
    evidence_location: str | None = None
    change_id: str | None = None
    branch: str | None = None
    worktree_path: str | None = None
    selected_worker_id: str | None = None
    error: str | None = None
    recorded_at: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", enum_value(self.phase, TddPhase, "TDD phase"))
        require_text(self.work_unit_id, "work unit id")
        require_text(self.status, "phase status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "work_unit_id": self.work_unit_id,
            "base_sha": self.base_sha,
            "status": self.status,
            "accepted_revision": self.accepted_revision,
            "evidence_location": self.evidence_location,
            "change_id": self.change_id,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "selected_worker_id": self.selected_worker_id,
            "error": self.error,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddPhaseState":
        return cls(
            phase=str(payload["phase"]),
            work_unit_id=str(payload["work_unit_id"]),
            base_sha=payload.get("base_sha"),
            status=str(payload["status"]),
            accepted_revision=payload.get("accepted_revision"),
            evidence_location=payload.get("evidence_location"),
            change_id=payload.get("change_id"),
            branch=payload.get("branch"),
            worktree_path=payload.get("worktree_path"),
            selected_worker_id=payload.get("selected_worker_id"),
            error=payload.get("error"),
            recorded_at=payload.get("recorded_at"),
        )


@dataclass(frozen=True)
class TddBehaviorProgress:
    behavior_id: str
    description: str
    current_phase: str
    status: str
    red_phase: TddPhaseState
    green_phase: TddPhaseState

    def __post_init__(self) -> None:
        require_text(self.behavior_id, "behavior id")
        require_text(self.description, "behavior description")
        object.__setattr__(self, "current_phase", enum_value(self.current_phase, TddPhase, "current TDD phase"))
        require_text(self.status, "behavior status")

    @classmethod
    def from_behavior(cls, behavior: TddBehavior) -> "TddBehaviorProgress":
        return cls(
            behavior_id=behavior.id,
            description=behavior.description,
            current_phase=TddPhase.RED.value,
            status="pending",
            red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=red_work_unit_id(behavior.id)),
            green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=green_work_unit_id(behavior.id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "behavior_id": self.behavior_id,
            "description": self.description,
            "current_phase": self.current_phase,
            "status": self.status,
            "red_phase": self.red_phase.to_dict(),
            "green_phase": self.green_phase.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddBehaviorProgress":
        return cls(
            behavior_id=str(payload["behavior_id"]),
            description=str(payload["description"]),
            current_phase=str(payload["current_phase"]),
            status=str(payload["status"]),
            red_phase=TddPhaseState.from_dict(dict(payload["red_phase"])),
            green_phase=TddPhaseState.from_dict(dict(payload["green_phase"])),
        )


def red_work_unit_id(behavior_id: str) -> str:
    require_text(behavior_id, "behavior id")
    return f"{behavior_id}--red"


def green_work_unit_id(behavior_id: str) -> str:
    require_text(behavior_id, "behavior id")
    return f"{behavior_id}--green"


def repair_work_unit_id(step_id: str, attempt_number: int) -> str:
    require_text(step_id, "step id")
    if attempt_number <= 0:
        raise ValueError("attempt number must be positive")
    return f"{step_id}--repair-{attempt_number}"
