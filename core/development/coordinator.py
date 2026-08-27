"""Minimal sequential coordinator for the Tiny Ticket proving slice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.development.work_unit import DevelopmentWorkUnit
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult


@dataclass(frozen=True)
class CoordinationResult:
    accepted_ids: set[str]
    attempts: list[WorkUnitExecutionResult]
    blocked_unit_id: str | None = None


class DevelopmentCoordinator:
    """Advance dependency-aware work one accepted unit at a time.

    Rack AI owns physical execution and retry/resource policy. ATHBA owns whether
    a rejected unit should later be clarified, split, redesigned or blocked.
    """

    def __init__(self, gateway: WorkUnitExecutionGateway):
        self.gateway = gateway

    async def run(self, units: Iterable[DevelopmentWorkUnit]) -> CoordinationResult:
        pending = list(units)
        accepted_ids: set[str] = set()
        attempts: list[WorkUnitExecutionResult] = []

        while pending:
            ready = next((unit for unit in pending if unit.is_ready(accepted_ids)), None)
            if ready is None:
                return CoordinationResult(accepted_ids, attempts, blocked_unit_id=pending[0].id)

            result = await self.gateway.execute(ready)
            attempts.append(result)
            if not result.accepted:
                return CoordinationResult(accepted_ids, attempts, blocked_unit_id=ready.id)

            accepted_ids.add(ready.id)
            pending.remove(ready)

        return CoordinationResult(accepted_ids, attempts)
