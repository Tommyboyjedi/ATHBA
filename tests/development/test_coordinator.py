from pathlib import Path

import pytest

from core.datastore.repos.work_unit_state_repo import WorkUnitStateRepo
from core.development.coordinator import DevelopmentCoordinator
from core.development.work_unit_coordination import DevelopmentCoordinatorDependencies
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class FakeGateway:
    def __init__(self, results=None, transport_error_for=None):
        self.results = results or {}
        self.transport_error_for = transport_error_for
        self.calls = []

    async def execute(self, work_unit, repository_binding):
        self.calls.append((work_unit.id, repository_binding.base_sha))
        if work_unit.id == self.transport_error_for:
            raise RuntimeError("transport exploded")
        return self.results.get(
            work_unit.id,
            WorkUnitExecutionResult(
                work_unit_id=work_unit.id,
                accepted=True,
                status="checks_passed",
                accepted_revision=(work_unit.id * 40)[:40],
            ),
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
        status=WorkUnitStatus.READY,
    )


def binding(base_sha="a" * 40):
    return RepositoryBinding(repository_id="tiny-ticket-fixture", base_ref="main", base_sha=base_sha)


@pytest.mark.asyncio
async def test_coordinator_executes_dependency_chain_with_accepted_revision_progression(tmp_path):
    gateway = FakeGateway(
        results={
            "a": WorkUnitExecutionResult(
                work_unit_id="a",
                accepted=True,
                status="checks_passed",
                accepted_revision="b" * 40,
            ),
            "b": WorkUnitExecutionResult(
                work_unit_id="b",
                accepted=True,
                status="checks_passed",
                accepted_revision="c" * 40,
            ),
        }
    )
    repo = WorkUnitStateRepo(tmp_path)
    result = await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=gateway, repository_binding=binding(), state_repo=repo)).run([unit("a"), unit("b", ["a"])])

    assert gateway.calls == [("a", "a" * 40), ("b", "b" * 40)]
    assert result.accepted_ids == {"a", "b"}
    assert result.final_revision == "c" * 40
    assert result.current_binding.base_sha == "c" * 40
    assert result.attempts[0].base_sha == "a" * 40
    assert result.attempts[1].base_sha == "b" * 40


@pytest.mark.asyncio
async def test_rejected_unit_blocks_progress_without_advancing_base(tmp_path):
    gateway = FakeGateway(
        results={
            "a": WorkUnitExecutionResult(
                work_unit_id="a",
                accepted=False,
                status="checks_failed",
                error="acceptance failed",
            )
        }
    )
    repo = WorkUnitStateRepo(tmp_path)
    result = await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=gateway, repository_binding=binding(), state_repo=repo)).run([unit("a"), unit("b", ["a"])])

    assert gateway.calls == [("a", "a" * 40)]
    assert result.accepted_ids == set()
    assert result.blocked_unit_id == "a"
    assert result.final_revision == "a" * 40
    assert result.work_units["a"].status == WorkUnitStatus.REJECTED.value


@pytest.mark.asyncio
async def test_accepted_result_without_revision_fails_closed_for_progression(tmp_path):
    gateway = FakeGateway(
        results={
            "a": WorkUnitExecutionResult(
                work_unit_id="a",
                accepted=True,
                status="checks_passed",
                accepted_revision=None,
            )
        }
    )
    repo = WorkUnitStateRepo(tmp_path)
    result = await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=gateway, repository_binding=binding(), state_repo=repo)).run([unit("a"), unit("b", ["a"])])

    assert gateway.calls == [("a", "a" * 40)]
    assert result.accepted_ids == {"a"}
    assert result.blocked_unit_id == "a"
    assert result.blocked_reason == "accepted work unit missing trusted accepted revision"
    assert result.final_revision == "a" * 40


@pytest.mark.asyncio
async def test_transport_failure_blocks_without_advancing_base(tmp_path):
    gateway = FakeGateway(transport_error_for="a")
    repo = WorkUnitStateRepo(tmp_path)
    result = await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=gateway, repository_binding=binding(), state_repo=repo)).run([unit("a"), unit("b", ["a"])])

    assert gateway.calls == [("a", "a" * 40)]
    assert result.blocked_unit_id == "a"
    assert result.attempts[-1].status == "transport_error"
    assert result.final_revision == "a" * 40
    assert result.work_units["a"].status == WorkUnitStatus.FAILED.value


@pytest.mark.asyncio
async def test_resume_skips_already_accepted_units_and_uses_persisted_revision(tmp_path):
    repo = WorkUnitStateRepo(tmp_path)
    first_gateway = FakeGateway(
        results={
            "a": WorkUnitExecutionResult(
                work_unit_id="a",
                accepted=True,
                status="checks_passed",
                accepted_revision="b" * 40,
            ),
            "b": WorkUnitExecutionResult(
                work_unit_id="b",
                accepted=False,
                status="blocked",
            ),
        }
    )
    first = await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=first_gateway, repository_binding=binding(), state_repo=repo)).run([unit("a"), unit("b", ["a"])])
    assert first_gateway.calls == [("a", "a" * 40), ("b", "b" * 40)]
    assert first.blocked_unit_id == "b"

    second_gateway = FakeGateway()
    resumed = await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=second_gateway, repository_binding=binding(), state_repo=repo)).run([unit("a"), unit("b", ["a"])])
    assert second_gateway.calls == []
    assert resumed.blocked_unit_id == "b"
    assert resumed.accepted_ids == {"a"}
    assert resumed.final_revision == "b" * 40


def test_state_repo_round_trips_snapshot(tmp_path):
    repo = WorkUnitStateRepo(tmp_path)
    gateway_repo_path = Path(tmp_path) / "tiny-ticket.json"

    snapshot_repo = WorkUnitStateRepo(tmp_path)
    fake_gateway = FakeGateway(
        results={
            "a": WorkUnitExecutionResult(
                work_unit_id="a",
                accepted=True,
                status="checks_passed",
                accepted_revision="b" * 40,
                change_id="change-a",
                evidence_location="/tmp/packet-a.json",
                selected_worker_id="worker-a",
                placement={"worker_ids": ["worker-a"]},
            )
        }
    )

    async def _run():
        return await DevelopmentCoordinator(DevelopmentCoordinatorDependencies(gateway=fake_gateway, repository_binding=binding(), state_repo=snapshot_repo)).run([unit("a")])

    import asyncio

    result = asyncio.run(_run())
    loaded = repo.load("tiny-ticket")
    assert gateway_repo_path.exists()
    assert loaded is not None
    assert loaded.current_trusted_revision == "b" * 40
    assert loaded.attempts[0].change_id == "change-a"
    assert loaded.attempts[0].placement == {"worker_ids": ["worker-a"]}
    assert result.work_units["a"].status == WorkUnitStatus.ACCEPTED.value
