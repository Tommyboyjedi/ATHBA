"""Compatibility exports for the legacy TDD coordinator path."""

from __future__ import annotations

from core.development.tdd_cycle_coordination import (
    DeveloperWorkUnitFactory,
    TddCoordinator,
    TddCoordinatorDependencies,
    TddCoordinationResult,
    TddStateRepository,
    TesterWorkUnitFactory,
)
from core.development.tdd_phase_execution import (
    RED_ALREADY_SATISFIED_FRAGMENT,
    PhaseExecutionRequest,
    PhaseOutcome as _PhaseOutcome,
    blocked_reason_for_result as _blocked_reason_for_result,
    is_red_already_satisfied as _is_red_already_satisfied,
    phase_state_from_result,
)
from core.development.tdd_progression import TddPhase
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult


def _phase_state_from_result(
    phase: TddPhase,
    work_unit_id: str,
    base_sha: str | None,
    recorded_at: str,
    result: WorkUnitExecutionResult,
):
    request = PhaseExecutionRequest(
        phase=phase,
        work_unit=DevelopmentWorkUnit(
            id=work_unit_id,
            project_id="compatibility-project",
            parent_ticket_id="compatibility-parent",
            objective="compatibility phase state",
            allowed_paths=["compatibility.py"],
            acceptance=AcceptanceContract(commands=[["compat-check"]]),
            status=WorkUnitStatus.READY,
        ),
        base_binding=RepositoryBinding(
            repository_id="compatibility-repository",
            base_ref="compatibility-base",
            base_sha=base_sha,
        ),
    )
    return phase_state_from_result(request, recorded_at, result)


__all__ = [
    "DeveloperWorkUnitFactory",
    "RED_ALREADY_SATISFIED_FRAGMENT",
    "TddCoordinator",
    "TddCoordinatorDependencies",
    "TddCoordinationResult",
    "TddStateRepository",
    "TesterWorkUnitFactory",
    "_PhaseOutcome",
    "_blocked_reason_for_result",
    "_is_red_already_satisfied",
    "_phase_state_from_result",
]
