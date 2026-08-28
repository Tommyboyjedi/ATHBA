"""State records for ATHBA's RED/GREEN TDD coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.development.progression import ExecutionAttemptRecord
from core.execution.rack_ai_contract import RepositoryBinding


class TddPhase(str, Enum):
    RED = "red"
    GREEN = "green"
    COMPLETE = "complete"


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
        _require_text(self.id, "behavior id")
        _require_text(self.project_id, "project id")
        _require_text(self.parent_ticket_id, "parent ticket id")
        _require_text(self.description, "behavior description")
        _require_text(self.test_name, "test name")
        _require_text(self.test_path, "test path")
        _require_text(self.production_path, "production path")
        _require_text(self.red_objective, "red objective")
        _require_text(self.green_objective, "green objective")
        _validate_commands(self.red_acceptance_commands, "red acceptance commands")
        _validate_commands(self.green_acceptance_commands, "green acceptance commands")


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


@dataclass(frozen=True)
class TddSnapshot:
    project_id: str
    repository_binding: RepositoryBinding
    current_trusted_revision: str | None
    completed_behavior_ids: list[str] = field(default_factory=list)
    attempts: list[ExecutionAttemptRecord] = field(default_factory=list)
    behaviors: dict[str, TddBehaviorProgress] = field(default_factory=dict)
    blocked_behavior_id: str | None = None
    blocked_phase: str | None = None
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "repository_binding": {
                "repository_id": self.repository_binding.repository_id,
                "base_ref": self.repository_binding.base_ref,
                "base_sha": self.repository_binding.base_sha,
                "registered_root": self.repository_binding.registered_root,
            },
            "current_trusted_revision": self.current_trusted_revision,
            "completed_behavior_ids": list(self.completed_behavior_ids),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "behaviors": {key: value.to_dict() for key, value in sorted(self.behaviors.items())},
            "blocked_behavior_id": self.blocked_behavior_id,
            "blocked_phase": self.blocked_phase,
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddSnapshot":
        binding = payload["repository_binding"]
        return cls(
            project_id=str(payload["project_id"]),
            repository_binding=RepositoryBinding(
                repository_id=str(binding["repository_id"]),
                base_ref=str(binding["base_ref"]),
                base_sha=binding.get("base_sha"),
                registered_root=binding.get("registered_root"),
            ),
            current_trusted_revision=payload.get("current_trusted_revision"),
            completed_behavior_ids=[str(item) for item in payload.get("completed_behavior_ids", [])],
            attempts=[ExecutionAttemptRecord.from_dict(item) for item in payload.get("attempts", [])],
            behaviors={
                str(key): TddBehaviorProgress.from_dict(value)
                for key, value in payload.get("behaviors", {}).items()
            },
            blocked_behavior_id=payload.get("blocked_behavior_id"),
            blocked_phase=payload.get("blocked_phase"),
            blocked_reason=payload.get("blocked_reason"),
        )


def red_work_unit_id(behavior_id: str) -> str:
    _require_text(behavior_id, "behavior id")
    return f"{behavior_id}--red"


def green_work_unit_id(behavior_id: str) -> str:
    _require_text(behavior_id, "behavior id")
    return f"{behavior_id}--green"


def _validate_commands(commands: list[list[str]], label: str) -> None:
    if not commands:
        raise ValueError(f"{label} must not be empty")
    for command in commands:
        if not command:
            raise ValueError(f"{label} must not contain empty commands")
        if any(not isinstance(arg, str) or not arg for arg in command):
            raise ValueError(f"{label} must contain non-empty string arguments")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
