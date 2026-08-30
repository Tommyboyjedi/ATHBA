"""Compatibility sequential work-unit coordination."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Iterable, Protocol

from core.datastore.repos.work_unit_state_repo import WorkUnitStateRepo
from core.development.progression import (
    CoordinationSnapshot,
    ExecutionAttemptRecord,
    ExecutionAttemptRequest,
    TransportFailureRequest,
    WorkUnitProgress,
    WorkUnitProgressRequest,
)
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


@dataclass(frozen=True)
class DevelopmentCoordinatorDependencies:
    gateway: WorkUnitExecutionGateway
    repository_binding: RepositoryBinding
    state_repo: CoordinationStateRepository


@dataclass(frozen=True)
class CoordinationContext:
    project_id: str
    accepted_ids: set[str]
    attempts: list[ExecutionAttemptRecord]
    current_binding: RepositoryBinding
    work_units: dict[str, WorkUnitProgress]


class DevelopmentCoordinator:
    """Advance dependency-aware work one accepted unit at a time."""

    def __init__(self, dependencies: DevelopmentCoordinatorDependencies):
        self.dependencies = dependencies

    async def run(self, units: Iterable[DevelopmentWorkUnit]) -> CoordinationResult:
        return await _run_units(self.dependencies, list(units))


async def _run_units(
    deps: DevelopmentCoordinatorDependencies,
    units: list[DevelopmentWorkUnit],
) -> CoordinationResult:
    if not units:
        return CoordinationResult(
            accepted_ids=set(),
            attempts=[],
            current_binding=deps.repository_binding,
            final_revision=deps.repository_binding.base_sha,
            work_units={},
        )
    snapshot = deps.state_repo.load(units[0].project_id)
    if snapshot is not None and snapshot.blocked_unit_id is not None:
        return _result_from_snapshot(snapshot)
    context = _coordination_context(deps.repository_binding, units, snapshot)
    pending = {unit.id: unit for unit in units}
    while True:
        pending_units = [
            unit
            for unit in pending.values()
            if context.work_units[unit.id].status not in _TERMINAL_STATUSES
        ]
        if not pending_units:
            result = _result_from_context(context)
            _save_result(deps.state_repo, result)
            return result
        ready = next((unit for unit in pending_units if unit.is_ready(context.accepted_ids)), None)
        if ready is None:
            blocked = _blocked_result(context, pending_units[0].id, "no dependency-ready work unit")
            _save_result(deps.state_repo, blocked)
            return blocked
        context, blocked = await _run_ready_unit(deps, context, ready)
        if blocked is not None:
            _save_result(deps.state_repo, blocked)
            return blocked


async def _run_ready_unit(
    deps: DevelopmentCoordinatorDependencies,
    context: CoordinationContext,
    ready: DevelopmentWorkUnit,
) -> tuple[CoordinationContext, CoordinationResult | None]:
    base_sha = context.current_binding.base_sha
    running = WorkUnitProgress.from_unit(
        WorkUnitProgressRequest(unit=ready, status=WorkUnitStatus.RUNNING, last_base_sha=base_sha)
    )
    context = replace(context, work_units={**context.work_units, ready.id: running})
    recorded_at = _utc_now()
    try:
        result = await deps.gateway.execute(ready, context.current_binding)
    except Exception as error:
        attempt = ExecutionAttemptRecord.transport_failure(
            TransportFailureRequest(
                work_unit_id=ready.id,
                base_sha=base_sha,
                recorded_at=recorded_at,
                error=str(error),
            )
        )
        failed = WorkUnitProgress.from_unit(
            WorkUnitProgressRequest(unit=ready, status=WorkUnitStatus.FAILED, last_base_sha=base_sha)
        )
        context = replace(
            context,
            attempts=[*context.attempts, attempt],
            work_units={**context.work_units, ready.id: failed},
        )
        return context, _blocked_result(context, ready.id, "work-unit transport failure")
    attempt = ExecutionAttemptRecord.from_result(
        ExecutionAttemptRequest(result=result, base_sha=base_sha, recorded_at=recorded_at)
    )
    context = replace(context, attempts=[*context.attempts, attempt])
    if not result.accepted:
        rejected = WorkUnitProgress.from_unit(
            WorkUnitProgressRequest(
                unit=ready,
                status=_terminal_status_for_result(result.status),
                last_base_sha=base_sha,
            )
        )
        context = replace(context, work_units={**context.work_units, ready.id: rejected})
        reason = f"work unit returned structured non-accepted result: {result.status}"
        return context, _blocked_result(context, ready.id, reason)
    accepted = WorkUnitProgress.from_unit(
        WorkUnitProgressRequest(unit=ready, status=WorkUnitStatus.ACCEPTED, last_base_sha=base_sha)
    )
    context = replace(
        context,
        accepted_ids={*context.accepted_ids, ready.id},
        work_units={**context.work_units, ready.id: accepted},
    )
    if not result.accepted_revision:
        return context, _blocked_result(
            context,
            ready.id,
            "accepted work unit missing trusted accepted revision",
        )
    binding = context.current_binding.with_base_sha(result.accepted_revision)
    return replace(context, current_binding=binding), None


def _coordination_context(
    binding: RepositoryBinding,
    units: list[DevelopmentWorkUnit],
    snapshot: CoordinationSnapshot | None,
) -> CoordinationContext:
    work_units = dict(snapshot.work_units) if snapshot else {}
    for unit in units:
        work_units.setdefault(
            unit.id,
            WorkUnitProgress.from_unit(WorkUnitProgressRequest(unit=unit, status=unit.status)),
        )
    return CoordinationContext(
        project_id=units[0].project_id,
        accepted_ids=set(snapshot.accepted_ids) if snapshot else set(),
        attempts=list(snapshot.attempts) if snapshot else [],
        current_binding=snapshot.repository_binding if snapshot else binding,
        work_units=work_units,
    )


def _result_from_context(context: CoordinationContext) -> CoordinationResult:
    return CoordinationResult(
        accepted_ids=context.accepted_ids,
        attempts=context.attempts,
        current_binding=context.current_binding,
        final_revision=context.current_binding.base_sha,
        work_units=context.work_units,
    )


def _result_from_snapshot(snapshot: CoordinationSnapshot) -> CoordinationResult:
    return CoordinationResult(
        accepted_ids=set(snapshot.accepted_ids),
        attempts=list(snapshot.attempts),
        current_binding=snapshot.repository_binding,
        final_revision=snapshot.current_trusted_revision,
        work_units=dict(snapshot.work_units),
        blocked_unit_id=snapshot.blocked_unit_id,
        blocked_reason=snapshot.blocked_reason,
    )


def _blocked_result(
    context: CoordinationContext,
    unit_id: str,
    reason: str,
) -> CoordinationResult:
    return CoordinationResult(
        accepted_ids=context.accepted_ids,
        attempts=context.attempts,
        current_binding=context.current_binding,
        final_revision=context.current_binding.base_sha,
        work_units=context.work_units,
        blocked_unit_id=unit_id,
        blocked_reason=reason,
    )


def _save_result(repository: CoordinationStateRepository, result: CoordinationResult) -> None:
    repository.save(
        CoordinationSnapshot(
            project_id=_project_id(result),
            repository_binding=result.current_binding,
            current_trusted_revision=result.final_revision,
            accepted_ids=result.accepted_ids,
            attempts=result.attempts,
            work_units=result.work_units,
            blocked_unit_id=result.blocked_unit_id,
            blocked_reason=result.blocked_reason,
        )
    )


def _project_id(result: CoordinationResult) -> str:
    if not result.work_units:
        raise ValueError("coordination results require work-unit progress before persistence")
    return next(iter(result.work_units.values())).project_id


def _terminal_status_for_result(status: str) -> WorkUnitStatus:
    if status in {"blocked"}:
        return WorkUnitStatus.BLOCKED
    if status in {"failed", "transport_error"}:
        return WorkUnitStatus.FAILED
    return WorkUnitStatus.REJECTED


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


_TERMINAL_STATUSES = {
    WorkUnitStatus.ACCEPTED.value,
    WorkUnitStatus.REJECTED.value,
    WorkUnitStatus.BLOCKED.value,
    WorkUnitStatus.FAILED.value,
}
