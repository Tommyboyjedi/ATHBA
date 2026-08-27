import pytest

from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit
from core.development.coordinator import DevelopmentCoordinator
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class FakeGateway:
    def __init__(self, rejected_id=None):
        self.rejected_id = rejected_id
        self.calls = []

    async def execute(self, work_unit):
        self.calls.append(work_unit.id)
        accepted = work_unit.id != self.rejected_id
        return WorkUnitExecutionResult(
            work_unit_id=work_unit.id,
            accepted=accepted,
            status="accepted" if accepted else "rejected",
            accepted_revision=("b" * 40) if accepted else None,
        )


def unit(unit_id, depends_on=None):
    return DevelopmentWorkUnit(
        id=unit_id,
        project_id="tiny-ticket",
        parent_ticket_id="story-1",
        objective=f"implement {unit_id}",
        allowed_paths=["src/app.py"],
        acceptance=AcceptanceContract(commands=[["pytest", f"tests/test_app.py::{unit_id}"]]),
        depends_on=depends_on or [],
    )


@pytest.mark.asyncio
async def test_coordinator_only_runs_dependency_after_acceptance():
    gateway = FakeGateway()
    result = await DevelopmentCoordinator(gateway).run([unit("a"), unit("b", ["a"])])

    assert gateway.calls == ["a", "b"]
    assert result.accepted_ids == {"a", "b"}
    assert result.blocked_unit_id is None


@pytest.mark.asyncio
async def test_rejected_unit_blocks_progress_instead_of_running_dependents():
    gateway = FakeGateway(rejected_id="a")
    result = await DevelopmentCoordinator(gateway).run([unit("a"), unit("b", ["a"])])

    assert gateway.calls == ["a"]
    assert result.accepted_ids == set()
    assert result.blocked_unit_id == "a"
