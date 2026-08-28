"""Sequential coordinator for the Tiny Ticket proving slice."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Protocol

from core.datastore.repos.work_unit_state_repo import WorkUnitStateRepo
from core.development.progression import CoordinationSnapshot, ExecutionAttemptRecord, WorkUnitProgress
from core.development.work_unit import DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway


@dataclass(frozen=True)
class CoordinationResult:
    accepted_ids: set[str]
    attempts: list[ExecutionAttemptRecord]
    current_binding: RepositoryBinding
    final_revision: str | None
    work_units: dict[str, WorkUnitProgress]
    blocked_unit_id: str | None = None
    blocked_reason: str | None = None


class CoordinationStateRepository(Protocol):
    def load(self, project_id: str) -> CoordinationSnapshot | None:
        ...

    def save(self, snapshot: CoordinationSnapshot):
        ...


class DevelopmentCoordinator:
    """Advance dependency-aware work one accepted unit at a time.

    Rack AI owns physical execution and retry/resource policy. ATHBA owns whether
    a rejected unit should later be clarified, split, redesigned or blocked.
    """

    def __init__(
        self,
        gateway: WorkUnitExecutionGateway,
        repository_binding: RepositoryBinding,
        state_repo: CoordinationStateRepository | None = None,
    ):
        self.gateway = gateway
        self.repository_binding = repository_binding
        self.state_repo = state_repo or WorkUnitStateRepo()

    async def run(self, units: Iterable[DevelopmentWorkUnit]) -> CoordinationResult:
        pending = {unit.id: unit for unit in units}
        if not pending:
            return CoordinationResult(
                accepted_ids=set(),
                attempts=[],
                current_binding=self.repository_binding,
                final_revision=self.repository_binding.base_sha,
                work_units={},
            )

        project_id = next(iter(pending.values())).project_id
        snapshot = self.state_repo.load(project_id)
        if snapshot is not None and snapshot.blocked_unit_id is not None:
            return self._result_from_snapshot(snapshot)

        accepted_ids = set(snapshot.accepted_ids) if snapshot else set()
        attempts = list(snapshot.attempts) if snapshot else []
        work_units = dict(snapshot.work_units) if snapshot else {}
        current_binding = snapshot.repository_binding if snapshot else self.repository_binding

        for unit in pending.values():
            work_units.setdefault(
                unit.id,
                WorkUnitProgress.from_unit(unit, status=unit.status),
            )

        while True:
            pending_units = [unit for unit in pending.values() if work_units[unit.id].status not in _TERMINAL_STATUSES]
            if not pending_units:
                result = CoordinationResult(
                    accepted_ids=accepted_ids,
                    attempts=attempts,
                    current_binding=current_binding,
                    final_revision=current_binding.base_sha,
                    work_units=work_units,
                )
                self._save_result(project_id, result)
                return result

            ready = next((unit for unit in pending_units if unit.is_ready(accepted_ids)), None)
            if ready is None:
                blocked = CoordinationResult(
                    accepted_ids=accepted_ids,
                    attempts=attempts,
                    current_binding=current_binding,
                    final_revision=current_binding.base_sha,
                    work_units=work_units,
                    blocked_unit_id=pending_units[0].id,
                    blocked_reason="no dependency-ready work unit",
                )
                self._save_result(project_id, blocked)
                return blocked

            base_sha = current_binding.base_sha
            work_units[ready.id] = WorkUnitProgress.from_unit(
                ready,
                status=WorkUnitStatus.RUNNING,
                last_base_sha=base_sha,
            )

            recorded_at = _utc_now()
            try:
                result = await self.gateway.execute(ready, current_binding)
            except Exception as error:
                attempts.append(
                    ExecutionAttemptRecord.transport_failure(
                        ready.id,
                        base_sha=base_sha,
                        recorded_at=recorded_at,
                        error=str(error),
                    )
                )
                work_units[ready.id] = WorkUnitProgress.from_unit(
                    ready,
                    status=WorkUnitStatus.FAILED,
                    last_base_sha=base_sha,
                )
                blocked = CoordinationResult(
                    accepted_ids=accepted_ids,
                    attempts=attempts,
                    current_binding=current_binding,
                    final_revision=current_binding.base_sha,
                    work_units=work_units,
                    blocked_unit_id=ready.id,
                    blocked_reason="work-unit transport failure",
                )
                self._save_result(project_id, blocked)
                return blocked

            attempt = ExecutionAttemptRecord.from_result(result, base_sha=base_sha, recorded_at=recorded_at)
            attempts.append(attempt)

            if not result.accepted:
                terminal_status = _terminal_status_for_result(result.status)
                work_units[ready.id] = WorkUnitProgress.from_unit(
                    ready,
                    status=terminal_status,
                    last_base_sha=base_sha,
                )
                blocked = CoordinationResult(
                    accepted_ids=accepted_ids,
                    attempts=attempts,
                    current_binding=current_binding,
                    final_revision=current_binding.base_sha,
                    work_units=work_units,
                    blocked_unit_id=ready.id,
                    blocked_reason=f"work unit returned structured non-accepted result: {result.status}",
                )
                self._save_result(project_id, blocked)
                return blocked

            accepted_ids.add(ready.id)
            work_units[ready.id] = WorkUnitProgress.from_unit(
                ready,
                status=WorkUnitStatus.ACCEPTED,
                last_base_sha=base_sha,
            )

            if not result.accepted_revision:
                blocked = CoordinationResult(
                    accepted_ids=accepted_ids,
                    attempts=attempts,
                    current_binding=current_binding,
                    final_revision=current_binding.base_sha,
                    work_units=work_units,
                    blocked_unit_id=ready.id,
                    blocked_reason="accepted work unit missing trusted accepted revision",
                )
                self._save_result(project_id, blocked)
                return blocked

            current_binding = current_binding.with_base_sha(result.accepted_revision)

    def _save_result(self, project_id: str, result: CoordinationResult) -> None:
        self.state_repo.save(
            CoordinationSnapshot(
                project_id=project_id,
                repository_binding=result.current_binding,
                current_trusted_revision=result.final_revision,
                accepted_ids=result.accepted_ids,
                attempts=result.attempts,
                work_units=result.work_units,
                blocked_unit_id=result.blocked_unit_id,
                blocked_reason=result.blocked_reason,
            )
        )

    def _result_from_snapshot(self, snapshot: CoordinationSnapshot) -> CoordinationResult:
        return CoordinationResult(
            accepted_ids=set(snapshot.accepted_ids),
            attempts=list(snapshot.attempts),
            current_binding=snapshot.repository_binding,
            final_revision=snapshot.current_trusted_revision,
            work_units=dict(snapshot.work_units),
            blocked_unit_id=snapshot.blocked_unit_id,
            blocked_reason=snapshot.blocked_reason,
        )


_TERMINAL_STATUSES = {
    WorkUnitStatus.ACCEPTED.value,
    WorkUnitStatus.REJECTED.value,
    WorkUnitStatus.BLOCKED.value,
    WorkUnitStatus.FAILED.value,
}


def _terminal_status_for_result(status: str) -> WorkUnitStatus:
    if status in {"blocked"}:
        return WorkUnitStatus.BLOCKED
    if status in {"failed", "transport_error"}:
        return WorkUnitStatus.FAILED
    return WorkUnitStatus.REJECTED


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
