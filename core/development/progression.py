"""Progression records for ATHBA's sequential work-unit coordinator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.development.work_unit import DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult


@dataclass(frozen=True)
class WorkUnitProgressRequest:
    unit: DevelopmentWorkUnit
    status: str | WorkUnitStatus
    last_base_sha: str | None = None


@dataclass(frozen=True)
class ExecutionAttemptRequest:
    result: WorkUnitExecutionResult
    base_sha: str | None
    recorded_at: str


@dataclass(frozen=True)
class TransportFailureRequest:
    work_unit_id: str
    base_sha: str | None
    recorded_at: str
    error: str


@dataclass(frozen=True)
class WorkUnitProgress:
    work_unit_id: str
    project_id: str
    parent_ticket_id: str
    objective: str
    depends_on: list[str]
    status: str
    last_base_sha: str | None = None

    @classmethod
    def from_unit(cls, request: WorkUnitProgressRequest) -> "WorkUnitProgress":
        status = request.status.value if isinstance(request.status, WorkUnitStatus) else request.status
        return cls(
            work_unit_id=request.unit.id,
            project_id=request.unit.project_id,
            parent_ticket_id=request.unit.parent_ticket_id,
            objective=request.unit.objective,
            depends_on=list(request.unit.depends_on),
            status=str(status),
            last_base_sha=request.last_base_sha,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_unit_id": self.work_unit_id,
            "project_id": self.project_id,
            "parent_ticket_id": self.parent_ticket_id,
            "objective": self.objective,
            "depends_on": list(self.depends_on),
            "status": self.status,
            "last_base_sha": self.last_base_sha,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkUnitProgress":
        return cls(
            work_unit_id=str(payload["work_unit_id"]),
            project_id=str(payload["project_id"]),
            parent_ticket_id=str(payload["parent_ticket_id"]),
            objective=str(payload["objective"]),
            depends_on=[str(item) for item in payload.get("depends_on", [])],
            status=str(payload["status"]),
            last_base_sha=payload.get("last_base_sha"),
        )


@dataclass(frozen=True)
class ExecutionAttemptRecord:
    work_unit_id: str
    base_sha: str | None
    accepted: bool
    status: str
    recorded_at: str
    change_id: str | None = None
    accepted_revision: str | None = None
    evidence_location: str | None = None
    branch: str | None = None
    worktree_path: str | None = None
    selected_worker_id: str | None = None
    placement: dict[str, Any] | None = None
    error: str | None = None

    @classmethod
    def from_result(cls, request: ExecutionAttemptRequest) -> "ExecutionAttemptRecord":
        return cls(
            work_unit_id=request.result.work_unit_id,
            base_sha=request.base_sha,
            accepted=request.result.accepted,
            status=request.result.status,
            recorded_at=request.recorded_at,
            change_id=request.result.change_id,
            accepted_revision=request.result.accepted_revision,
            evidence_location=request.result.evidence_location,
            branch=request.result.branch,
            worktree_path=request.result.worktree_path,
            selected_worker_id=request.result.selected_worker_id,
            placement=dict(request.result.placement) if request.result.placement is not None else None,
            error=request.result.error,
        )

    @classmethod
    def transport_failure(cls, request: TransportFailureRequest) -> "ExecutionAttemptRecord":
        return cls(
            work_unit_id=request.work_unit_id,
            base_sha=request.base_sha,
            accepted=False,
            status="transport_error",
            recorded_at=request.recorded_at,
            error=request.error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_unit_id": self.work_unit_id,
            "base_sha": self.base_sha,
            "accepted": self.accepted,
            "status": self.status,
            "recorded_at": self.recorded_at,
            "change_id": self.change_id,
            "accepted_revision": self.accepted_revision,
            "evidence_location": self.evidence_location,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "selected_worker_id": self.selected_worker_id,
            "placement": dict(self.placement) if self.placement is not None else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ExecutionAttemptRecord":
        placement = payload.get("placement")
        if placement is not None and not isinstance(placement, dict):
            raise ValueError("placement must be an object when persisted")
        return cls(
            work_unit_id=str(payload["work_unit_id"]),
            base_sha=payload.get("base_sha"),
            accepted=bool(payload["accepted"]),
            status=str(payload["status"]),
            recorded_at=str(payload["recorded_at"]),
            change_id=payload.get("change_id"),
            accepted_revision=payload.get("accepted_revision"),
            evidence_location=payload.get("evidence_location"),
            branch=payload.get("branch"),
            worktree_path=payload.get("worktree_path"),
            selected_worker_id=payload.get("selected_worker_id"),
            placement=dict(placement) if placement is not None else None,
            error=payload.get("error"),
        )


@dataclass(frozen=True)
class CoordinationSnapshot:
    project_id: str
    repository_binding: RepositoryBinding
    current_trusted_revision: str | None
    accepted_ids: set[str] = field(default_factory=set)
    attempts: list[ExecutionAttemptRecord] = field(default_factory=list)
    work_units: dict[str, WorkUnitProgress] = field(default_factory=dict)
    blocked_unit_id: str | None = None
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
            "accepted_ids": sorted(self.accepted_ids),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "work_units": {key: value.to_dict() for key, value in sorted(self.work_units.items())},
            "blocked_unit_id": self.blocked_unit_id,
            "blocked_reason": self.blocked_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CoordinationSnapshot":
        binding_payload = dict(payload["repository_binding"])
        return cls(
            project_id=str(payload["project_id"]),
            repository_binding=RepositoryBinding(
                repository_id=str(binding_payload["repository_id"]),
                base_ref=str(binding_payload["base_ref"]),
                base_sha=str(binding_payload["base_sha"]),
                registered_root=str(binding_payload["registered_root"]),
            ),
            current_trusted_revision=payload.get("current_trusted_revision"),
            accepted_ids={str(item) for item in payload.get("accepted_ids", [])},
            attempts=[ExecutionAttemptRecord.from_dict(item) for item in payload.get("attempts", [])],
            work_units={str(key): WorkUnitProgress.from_dict(value) for key, value in payload.get("work_units", {}).items()},
            blocked_unit_id=payload.get("blocked_unit_id"),
            blocked_reason=payload.get("blocked_reason"),
        )
