"""Shared RED/GREEN phase execution semantics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from core.development.progression import ExecutionAttemptRecord
from core.development.tdd_progression import TddPhase, TddPhaseState
from core.development.work_unit import DevelopmentWorkUnit
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult

RED_ALREADY_SATISFIED_FRAGMENT = "RED check failed: test unexpectedly passed"


@dataclass(frozen=True)
class PhaseExecutionRequest:
    phase: TddPhase
    work_unit: DevelopmentWorkUnit
    base_binding: RepositoryBinding


@dataclass(frozen=True)
class PhaseOutcome:
    attempt: ExecutionAttemptRecord | None
    phase_state: TddPhaseState
    accepted: bool
    blocked_reason: str | None = None
    execution_result: WorkUnitExecutionResult | None = None


class TddPhaseExecutor:
    def __init__(self, gateway: WorkUnitExecutionGateway):
        self.gateway = gateway

    async def execute(self, request: PhaseExecutionRequest) -> PhaseOutcome:
        recorded_at = _utc_now()
        base_sha = request.base_binding.base_sha
        try:
            result = await self.gateway.execute(request.work_unit, request.base_binding)
        except Exception as error:
            attempt = ExecutionAttemptRecord.transport_failure(
                request.work_unit.id,
                base_sha=base_sha,
                recorded_at=recorded_at,
                error=str(error),
            )
            return PhaseOutcome(
                attempt=attempt,
                phase_state=transport_failure_state(request, recorded_at, str(error)),
                accepted=False,
                blocked_reason=f"{request.phase.value} phase transport failure",
            )
        attempt = ExecutionAttemptRecord.from_result(
            result,
            base_sha=base_sha,
            recorded_at=recorded_at,
        )
        phase_state = phase_state_from_result(request, recorded_at, result)
        if not result.accepted:
            return PhaseOutcome(
                attempt=attempt,
                phase_state=phase_state,
                accepted=False,
                blocked_reason=blocked_reason_for_result(request.phase, result),
                execution_result=result,
            )
        if not result.accepted_revision:
            return PhaseOutcome(
                attempt=attempt,
                phase_state=phase_state,
                accepted=False,
                blocked_reason=f"accepted {request.phase.value} phase missing trusted accepted revision",
                execution_result=result,
            )
        return PhaseOutcome(
            attempt=attempt,
            phase_state=phase_state,
            accepted=True,
            execution_result=result,
        )


def phase_state_from_result(
    request: PhaseExecutionRequest,
    recorded_at: str,
    result: WorkUnitExecutionResult,
) -> TddPhaseState:
    return TddPhaseState(
        phase=request.phase.value,
        work_unit_id=request.work_unit.id,
        base_sha=request.base_binding.base_sha,
        status=phase_status_for_result(request.phase, result),
        accepted_revision=result.accepted_revision,
        evidence_location=result.evidence_location,
        change_id=result.change_id,
        branch=result.branch,
        worktree_path=result.worktree_path,
        selected_worker_id=result.selected_worker_id,
        error=result.error,
        recorded_at=recorded_at,
    )


def transport_failure_state(
    request: PhaseExecutionRequest,
    recorded_at: str,
    error: str,
) -> TddPhaseState:
    return TddPhaseState(
        phase=request.phase.value,
        work_unit_id=request.work_unit.id,
        base_sha=request.base_binding.base_sha,
        status="transport_error",
        error=error,
        recorded_at=recorded_at,
    )


def phase_status_for_result(phase: TddPhase, result: WorkUnitExecutionResult) -> str:
    if phase == TddPhase.RED and is_red_already_satisfied(result):
        return "already_satisfied"
    return result.status


def blocked_reason_for_result(phase: TddPhase, result: WorkUnitExecutionResult) -> str:
    if phase == TddPhase.RED and is_red_already_satisfied(result):
        return "red phase found behavior already satisfied before RED"
    return f"{phase.value} phase returned structured non-accepted result: {result.status}"


def is_red_already_satisfied(result: WorkUnitExecutionResult) -> bool:
    return (
        not result.accepted
        and result.status == "checks_failed"
        and RED_ALREADY_SATISFIED_FRAGMENT in (result.error or "")
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
