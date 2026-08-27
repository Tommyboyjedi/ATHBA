"""Domain records for deliberately small development work units."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkUnitStatus(str, Enum):
    PLANNED = "planned"
    READY = "ready"
    RUNNING = "running"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class AcceptanceContract:
    commands: list[list[str]]
    required_artifacts: list[str] = field(default_factory=list)


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
    status: WorkUnitStatus = WorkUnitStatus.PLANNED

    def is_ready(self, accepted_dependencies: set[str]) -> bool:
        """Return true when every declared dependency has been accepted."""
        return all(dependency in accepted_dependencies for dependency in self.depends_on)


@dataclass(frozen=True)
class ExecutionAttempt:
    work_unit_id: str
    accepted: bool
    status: str
    change_id: str | None = None
    selected_worker_id: str | None = None
    placement: str | None = None
    branch: str | None = None
    accepted_revision: str | None = None
    packet_path: str | None = None
    error: str | None = None
