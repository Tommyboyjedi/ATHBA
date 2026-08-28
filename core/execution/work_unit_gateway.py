"""Execution boundary between ATHBA and an external work-unit executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WorkUnitExecutionResult:
    """Executor-neutral result returned to the ATHBA application layer."""

    work_unit_id: str
    accepted: bool
    status: str
    change_id: str | None = None
    branch: str | None = None
    accepted_revision: str | None = None
    evidence_location: str | None = None


class WorkUnitExecutionGateway(Protocol):
    """Port implemented by Rack AI adapters and deterministic test fakes."""

    async def execute(self, work_unit: object) -> WorkUnitExecutionResult:
        """Execute one ready bounded work unit and return structured evidence."""
        ...
