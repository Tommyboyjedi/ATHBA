from pathlib import Path

import pytest

from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.progression import ExecutionAttemptRecord
from core.development.tdd_coordinator import DeveloperWorkUnitFactory, TddCoordinator, TesterWorkUnitFactory
from core.development.tdd_progression import TddBehavior, TddBehaviorProgress, TddPhase, TddPhaseState, TddSnapshot
from core.execution.rack_ai_contract import (
    RepositoryBinding,
    find_forbidden_resource_selection_keys,
    to_rack_ai_request,
)
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
        return self.results[work_unit.id]


def behavior(behavior_id: str, description: str, test_name: str) -> TddBehavior:
    return TddBehavior(
        id=behavior_id,
        project_id="task-queue",
        parent_ticket_id="story-1",
        description=description,
        test_name=test_name,
        test_path="tests/test_task_queue.py",
        production_path="task_queue.py",
        red_objective=f"Add one failing pytest test for {description}.",
        green_objective=f"Implement only enough TaskQueue code for {description}.",
        red_acceptance_commands=[["python", "scripts/assert_test_fails.py", test_name, "expected failure"]],
        green_acceptance_commands=[["pytest", "-q", test_name], ["pytest", "-q", "tests/test_task_queue.py"]],
    )


def binding(base_sha="a" * 40) -> RepositoryBinding:
    return RepositoryBinding(repository_id="task-queue-fixture", base_ref="main", base_sha=base_sha)


def accepted(work_unit_id: str, revision: str) -> WorkUnitExecutionResult:
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=True,
        status="checks_passed",
        accepted_revision=revision,
        change_id=f"change-{work_unit_id}",
        evidence_location=f"/tmp/{work_unit_id}.json",
    )


def rejected(work_unit_id: str, status="checks_failed") -> WorkUnitExecutionResult:
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=False,
        status=status,
        change_id=f"change-{work_unit_id}",
        error="acceptance failed",
    )


@pytest.mark.asyncio
async def test_red_runs_before_green(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    gateway = FakeGateway(
        results={
            "b1--red": accepted("b1--red", "b" * 40),
            "b1--green": accepted("b1--green", "c" * 40),
        }
    )

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert gateway.calls == [("b1--red", "a" * 40), ("b1--green", "b" * 40)]
    assert result.completed_behavior_ids == ["b1"]


@pytest.mark.asyncio
async def test_green_base_matches_red_accepted_revision_and_next_red_uses_prior_green_revision(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    b2 = behavior("b2", "duplicate id", "tests/test_task_queue.py::test_duplicate_task_id")
    gateway = FakeGateway(
        results={
            "b1--red": accepted("b1--red", "b" * 40),
            "b1--green": accepted("b1--green", "c" * 40),
            "b2--red": accepted("b2--red", "d" * 40),
            "b2--green": accepted("b2--green", "e" * 40),
        }
    )

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1, b2])

    assert gateway.calls == [
        ("b1--red", "a" * 40),
        ("b1--green", "b" * 40),
        ("b2--red", "c" * 40),
        ("b2--green", "d" * 40),
    ]
    assert result.final_revision == "e" * 40


@pytest.mark.asyncio
async def test_rejected_red_stops_cycle(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    gateway = FakeGateway(results={"b1--red": rejected("b1--red")})

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert gateway.calls == [("b1--red", "a" * 40)]
    assert result.blocked_behavior_id == "b1"
    assert result.blocked_phase == TddPhase.RED.value
    assert result.final_revision == "a" * 40


@pytest.mark.asyncio
async def test_red_unexpected_pass_is_reported_as_already_satisfied(tmp_path):
    b1 = behavior("b1", "pending order", "tests/test_task_queue.py::test_pending_order")
    gateway = FakeGateway(
        results={
            "b1--red": WorkUnitExecutionResult(
                work_unit_id="b1--red",
                accepted=False,
                status="checks_failed",
                change_id="change-b1--red",
                error="RED check failed: test unexpectedly passed",
            )
        }
    )

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert result.blocked_phase == TddPhase.RED.value
    assert result.blocked_reason == "red phase found behavior already satisfied before RED"
    assert result.behaviors["b1"].red_phase.status == "already_satisfied"


@pytest.mark.asyncio
async def test_accepted_red_without_revision_stops_cycle(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    gateway = FakeGateway(
        results={
            "b1--red": WorkUnitExecutionResult(
                work_unit_id="b1--red",
                accepted=True,
                status="checks_passed",
                accepted_revision=None,
            )
        }
    )

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert gateway.calls == [("b1--red", "a" * 40)]
    assert result.blocked_phase == TddPhase.RED.value
    assert result.blocked_reason == "accepted red phase missing trusted accepted revision"


@pytest.mark.asyncio
async def test_rejected_green_stops_cycle(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    gateway = FakeGateway(
        results={
            "b1--red": accepted("b1--red", "b" * 40),
            "b1--green": rejected("b1--green"),
        }
    )

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert gateway.calls == [("b1--red", "a" * 40), ("b1--green", "b" * 40)]
    assert result.blocked_phase == TddPhase.GREEN.value
    assert result.final_revision == "b" * 40


@pytest.mark.asyncio
async def test_accepted_green_without_revision_stops_cycle(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    gateway = FakeGateway(
        results={
            "b1--red": accepted("b1--red", "b" * 40),
            "b1--green": WorkUnitExecutionResult(
                work_unit_id="b1--green",
                accepted=True,
                status="checks_passed",
                accepted_revision=None,
            ),
        }
    )

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert result.blocked_phase == TddPhase.GREEN.value
    assert result.blocked_reason == "accepted green phase missing trusted accepted revision"


def test_red_and_green_work_units_use_phase_specific_paths_only():
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")

    red = TesterWorkUnitFactory().build(b1)
    green = DeveloperWorkUnitFactory().build(b1)

    assert red.allowed_paths == ["tests/test_task_queue.py"]
    assert green.allowed_paths == ["task_queue.py"]


def test_phase_requests_do_not_leak_physical_resource_selection():
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    request = to_rack_ai_request("task-queue", binding(), TesterWorkUnitFactory().build(b1))
    request_green = to_rack_ai_request("task-queue", binding(), DeveloperWorkUnitFactory().build(b1))

    assert find_forbidden_resource_selection_keys(request) == []
    assert find_forbidden_resource_selection_keys(request_green) == []


def test_state_persists_phase_and_revisions(tmp_path):
    repo = TddStateRepo(tmp_path)
    snapshot = TddSnapshot(
        project_id="task-queue",
        repository_binding=binding("c" * 40),
        current_trusted_revision="c" * 40,
        completed_behavior_ids=["b1"],
        attempts=[
            ExecutionAttemptRecord(
                work_unit_id="b1--red",
                base_sha="a" * 40,
                accepted=True,
                status="checks_passed",
                recorded_at="2026-08-28T00:00:00+00:00",
                accepted_revision="b" * 40,
                evidence_location="/tmp/red.json",
            )
        ],
        behaviors={
            "b1": TddBehaviorProgress(
                behavior_id="b1",
                description="add task",
                current_phase=TddPhase.COMPLETE.value,
                status="completed",
                red_phase=TddPhaseState(
                    phase=TddPhase.RED.value,
                    work_unit_id="b1--red",
                    base_sha="a" * 40,
                    status="checks_passed",
                    accepted_revision="b" * 40,
                ),
                green_phase=TddPhaseState(
                    phase=TddPhase.GREEN.value,
                    work_unit_id="b1--green",
                    base_sha="b" * 40,
                    status="checks_passed",
                    accepted_revision="c" * 40,
                ),
            )
        },
    )

    repo.save(snapshot)
    loaded = repo.load("task-queue")

    assert loaded is not None
    assert loaded.current_trusted_revision == "c" * 40
    assert loaded.behaviors["b1"].green_phase.accepted_revision == "c" * 40
    assert loaded.behaviors["b1"].current_phase == TddPhase.COMPLETE.value


def test_state_persists_repository_environment_resources(tmp_path):
    repo = TddStateRepo(tmp_path)
    snapshot = TddSnapshot(
        project_id="task-queue",
        repository_binding=RepositoryBinding(
            repository_id="task-queue-fixture",
            base_ref="main",
            base_sha="c" * 40,
            environment_resources=["/srv/env/python-314", "/srv/env/pytest"],
        ),
        current_trusted_revision="c" * 40,
    )

    repo.save(snapshot)
    loaded = repo.load("task-queue")

    assert loaded is not None
    assert loaded.repository_binding.environment_resources == ["/srv/env/python-314", "/srv/env/pytest"]


@pytest.mark.asyncio
async def test_resume_does_not_rerun_completed_red(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    repo = TddStateRepo(tmp_path)
    repo.save(
        TddSnapshot(
            project_id="task-queue",
            repository_binding=binding("b" * 40),
            current_trusted_revision="b" * 40,
            behaviors={
                "b1": TddBehaviorProgress(
                    behavior_id="b1",
                    description=b1.description,
                    current_phase=TddPhase.GREEN.value,
                    status="red_accepted",
                    red_phase=TddPhaseState(
                        phase=TddPhase.RED.value,
                        work_unit_id="b1--red",
                        base_sha="a" * 40,
                        status="checks_passed",
                        accepted_revision="b" * 40,
                    ),
                    green_phase=TddPhaseState(
                        phase=TddPhase.GREEN.value,
                        work_unit_id="b1--green",
                    ),
                )
            },
        )
    )
    gateway = FakeGateway(results={"b1--green": accepted("b1--green", "c" * 40)})

    result = await TddCoordinator(gateway, binding(), repo).run([b1])

    assert gateway.calls == [("b1--green", "b" * 40)]
    assert result.completed_behavior_ids == ["b1"]


@pytest.mark.asyncio
async def test_resume_does_not_rerun_completed_green(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    b2 = behavior("b2", "duplicate", "tests/test_task_queue.py::test_duplicate_task_id")
    repo = TddStateRepo(tmp_path)
    repo.save(
        TddSnapshot(
            project_id="task-queue",
            repository_binding=binding("c" * 40),
            current_trusted_revision="c" * 40,
            completed_behavior_ids=["b1"],
            behaviors={
                "b1": TddBehaviorProgress(
                    behavior_id="b1",
                    description=b1.description,
                    current_phase=TddPhase.COMPLETE.value,
                    status="completed",
                    red_phase=TddPhaseState(
                        phase=TddPhase.RED.value,
                        work_unit_id="b1--red",
                        base_sha="a" * 40,
                        status="checks_passed",
                        accepted_revision="b" * 40,
                    ),
                    green_phase=TddPhaseState(
                        phase=TddPhase.GREEN.value,
                        work_unit_id="b1--green",
                        base_sha="b" * 40,
                        status="checks_passed",
                        accepted_revision="c" * 40,
                    ),
                )
            },
        )
    )
    gateway = FakeGateway(
        results={
            "b2--red": accepted("b2--red", "d" * 40),
            "b2--green": accepted("b2--green", "e" * 40),
        }
    )

    result = await TddCoordinator(gateway, binding(), repo).run([b1, b2])

    assert gateway.calls == [("b2--red", "c" * 40), ("b2--green", "d" * 40)]
    assert result.completed_behavior_ids == ["b1", "b2"]


@pytest.mark.asyncio
async def test_transport_failure_blocks_phase(tmp_path):
    b1 = behavior("b1", "add task", "tests/test_task_queue.py::test_add_task")
    gateway = FakeGateway(results={}, transport_error_for="b1--red")

    result = await TddCoordinator(gateway, binding(), TddStateRepo(tmp_path)).run([b1])

    assert result.blocked_phase == TddPhase.RED.value
    assert result.attempts[-1].status == "transport_error"
