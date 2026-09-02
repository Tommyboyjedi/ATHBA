"""Domain records for deliberately small development work units."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


SUPPORTED_CAPABILITIES = {"implementation"}
SUPPORTED_COMPLEXITIES = {"small", "medium", "large"}
SUPPORTED_NETWORK_POLICIES = {"disabled"}


class WorkUnitStatus(str, Enum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class AcceptanceContract:
    commands: list[list[str]]
    required_artifacts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.commands:
            raise ValueError("acceptance commands must not be empty")
        for command in self.commands:
            if not command:
                raise ValueError("acceptance commands must not contain empty commands")
            if any(not isinstance(arg, str) or not arg for arg in command):
                raise ValueError("acceptance commands must contain non-empty string arguments")
        if any(not isinstance(path, str) or not path for path in self.required_artifacts):
            raise ValueError("required artifacts must contain non-empty paths")


@dataclass(frozen=True)
class DevelopmentWorkUnit:
    id: str
    project_id: str
    parent_ticket_id: str
    objective: str
    allowed_paths: list[str]
    acceptance: AcceptanceContract
    depends_on: list[str] = field(default_factory=list)
    complexity: str = "small"
    capability: str = "implementation"
    requires_large_context: bool = False
    max_implementation_attempts: int = 2
    timeout_seconds: int = 900
    network: str = "disabled"
    change_key: str | None = None
    status: WorkUnitStatus = WorkUnitStatus.PLANNED

    def __post_init__(self) -> None:
        _require_text(self.id, "work unit id")
        _require_text(self.project_id, "project id")
        _require_text(self.parent_ticket_id, "parent ticket id")
        _require_text(self.objective, "objective")
        if not self.allowed_paths:
            raise ValueError("allowed paths must not be empty")
        if any(not isinstance(path, str) or not path for path in self.allowed_paths):
            raise ValueError("allowed paths must contain non-empty paths")
        if self.id in self.depends_on:
            raise ValueError("work unit cannot depend on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("work unit dependencies must be unique")
        if any(not isinstance(item, str) or not item for item in self.depends_on):
            raise ValueError("work unit dependencies must contain non-empty ids")
        if self.capability not in SUPPORTED_CAPABILITIES:
            raise ValueError(f"unsupported work unit capability: {self.capability}")
        if self.complexity not in SUPPORTED_COMPLEXITIES:
            raise ValueError(f"unsupported work unit complexity: {self.complexity}")
        if self.network not in SUPPORTED_NETWORK_POLICIES:
            raise ValueError(f"unsupported work unit network policy: {self.network}")
        if self.max_implementation_attempts <= 0:
            raise ValueError("max implementation attempts must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout seconds must be positive")
        if self.change_key is not None:
            _require_text(self.change_key, "work unit change key")

    def dependencies_satisfied(self, accepted_dependencies: set[str]) -> bool:
        """Return true when every declared dependency has been accepted."""
        return all(dependency in accepted_dependencies for dependency in self.depends_on)

    def is_ready(self, accepted_dependencies: set[str]) -> bool:
        """Return true when the unit is marked ready and its dependencies are satisfied."""
        return self.status == WorkUnitStatus.READY and self.dependencies_satisfied(accepted_dependencies)

    def is_ready_for_execution(self) -> bool:
        """Return true when ATHBA has marked the unit as ready for submission."""
        return self.status == WorkUnitStatus.READY


@dataclass(frozen=True)
class WorkerExecutionProvenance:
    """Durable worker identity reported by one Rack AI packet."""
    worker_id: str
    worker_role: str
    worker_kind: str
    model_id: str
    provider_profile: str
    resource_id: str
    backend: str
    tool_profile: str | None = None


@dataclass(frozen=True)
class ExecutionAttempt:
    work_unit_id: str
    accepted: bool
    status: str
    change_id: str | None = None
    selected_worker_id: str | None = None
    placement: dict[str, Any] | None = None
    branch: str | None = None
    accepted_revision: str | None = None
    packet_path: str | None = None
    worktree_path: str | None = None
    error: str | None = None
    worker_provenance: WorkerExecutionProvenance | None = None


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
