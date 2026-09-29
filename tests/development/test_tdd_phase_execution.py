from __future__ import annotations

import pytest

from core.development.athba_workspace_routing import AthbaModelWorkKind, AthbaWorkspaceIdentity
from core.development.tdd_phase_execution import PhaseExecutionRequest, TddPhaseExecutor
from core.development.tdd_progression import TddPhase
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.rack_ai_runtime import RackAiResourceWait


class WaitingGateway:
    async def execute(self, work_unit, repository_binding):
        raise RackAiResourceWait("workspace closure pending")


def _unit() -> DevelopmentWorkUnit:
    return DevelopmentWorkUnit(
        "green-1",
        "project",
        "ticket",
        "implement behavior",
        ["running_total.py"],
        AcceptanceContract([["python", "-m", "pytest"]]),
        model_work_kind=AthbaModelWorkKind.FRONTIER_IMPLEMENTATION,
        workspace_identity=AthbaWorkspaceIdentity("work", "submission", "attempt"),
        status=WorkUnitStatus.READY,
    )


@pytest.mark.asyncio
async def test_phase_executor_preserves_rackai_resource_wait_without_attempt_record():
    executor = TddPhaseExecutor(WaitingGateway())

    with pytest.raises(RackAiResourceWait, match="closure pending"):
        await executor.execute(
            PhaseExecutionRequest(
                TddPhase.GREEN,
                _unit(),
                RepositoryBinding("repo", "main", "a" * 40),
            )
        )
