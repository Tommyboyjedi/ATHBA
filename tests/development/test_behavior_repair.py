from dataclasses import replace
from pathlib import Path

import pytest

from core.development.behavior_completion import REPAIR_REQUIRED
from core.development.behavior_repair import (
    BehaviorRepairDependencies,
    BehaviorRepairRequest,
    BehaviorRepairService,
)
from core.development.deterministic_regression import DeterministicRegressionService
from core.development.microcycle_domain import (
    BehaviorRepairProgress,
    BehaviorReviewState,
    RegressionCommandReport,
    RegressionState,
    ScenarioCompletion,
)
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult
from tests.development.test_strict_microcycle import CandidateRepository, initial_state


class Store:
    def __init__(self):
        self.saved = []

    def save(self, state):
        self.saved.append(state)


class Gateway:
    def __init__(self, accepted=True):
        self.accepted = accepted
        self.units = []

    async def execute(self, unit, binding):
        self.units.append((unit, binding))
        return WorkUnitExecutionResult(
            unit.id,
            accepted=self.accepted,
            status="checks_passed" if self.accepted else "checks_failed",
            accepted_revision="repair" if self.accepted else None,
            evidence_location="repair/evidence",
            error=None if self.accepted else "candidate rejected",
        )


class Runtime:
    def __init__(self, statuses=()):
        self.statuses = dict(statuses)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        status = self.statuses.get(request.target, "passed")
        return RegressionCommandReport(
            request.target,
            request.command,
            0 if status == "passed" else 1,
            status,
            f"runtime/{request.target}",
        )


def reviewed_state():
    return replace(
        initial_state(),
        completion=ScenarioCompletion("scenario_complete", "base"),
        regression=RegressionState("regression_clear", ("pytest", "-q")),
        behavior_review=BehaviorReviewState(
            verdict=REPAIR_REQUIRED,
            rationale="the state transition is semantically incomplete",
            findings=("the approved scenario omits the required durable transition",),
            evidence_refs=("review/1",),
            reviewed_candidate_revision="base",
        ),
    )


def request(tmp_path, state):
    return BehaviorRepairRequest(
        "toy-project",
        "widget.py",
        tmp_path,
        RepositoryBinding("toy-project", "main", "base"),
        state,
        PythonPytestAdapter(),
    )


@pytest.mark.asyncio
async def test_behavior_repair_is_production_only_then_regressed_and_ready_for_rereview(tmp_path):
    store, gateway, runtime = Store(), Gateway(), Runtime()
    candidates = CandidateRepository(tmp_path, {"repair": "class Widget:\n    pass\n"})
    service = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, DeterministicRegressionService(runtime))
    )

    outcome = await service.repair(request(tmp_path, reviewed_state()))

    assert outcome.status == "behavior_repair_regression_clear"
    assert outcome.state.behavior_review.verdict == "pending"
    assert outcome.state.behavior_review.repair.attempts == 1
    assert outcome.state.behavior_review.repair.current_candidate_revision
    unit, binding = gateway.units[0]
    assert unit.allowed_paths == ["widget.py"]
    assert "do not edit tests" in unit.objective
    assert "durable transition" in unit.objective
    assert binding.base_sha == "base"
    assert [item.target for item in runtime.requests] == [
        "tests/test_widget.py::test_widget",
        "accepted_regression_suite",
    ]
    assert any(item.behavior_review.repair.current_candidate_revision == "repair" for item in store.saved)


@pytest.mark.asyncio
async def test_repair_candidate_rejection_keeps_same_behavior_incomplete(tmp_path):
    store, gateway = Store(), Gateway(False)
    candidates = CandidateRepository(tmp_path, {"base": ""})
    service = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, DeterministicRegressionService(Runtime()))
    )

    outcome = await service.repair(request(tmp_path, reviewed_state()))

    assert outcome.status == "behavior_repair_candidate_rejected"
    assert outcome.state.completion.status == "scenario_complete"
    assert outcome.state.behavior_review.verdict == REPAIR_REQUIRED
    assert outcome.state.behavior_review.repair.attempts == 1


@pytest.mark.asyncio
async def test_behavior_repair_cap_survives_restart_and_forbids_attempt_five(tmp_path):
    store, gateway = Store(), Gateway(False)
    candidates = CandidateRepository(tmp_path, {"base": ""})
    service = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, DeterministicRegressionService(Runtime()))
    )
    state = reviewed_state()

    for _ in range(4):
        outcome = await service.repair(request(tmp_path, state))
        state = outcome.state
        assert outcome.status == "behavior_repair_candidate_rejected"
    exhausted = await service.repair(request(tmp_path, state))

    assert exhausted.status == "behavior_repair_attempts_exhausted"
    assert len(gateway.units) == 4
    assert exhausted.state.behavior_review.repair.attempts == 4


@pytest.mark.asyncio
async def test_resume_after_accepted_candidate_regresses_without_a_second_developer_submission(tmp_path):
    state = reviewed_state()
    state = replace(
        state,
        behavior_review=replace(
            state.behavior_review,
            verdict="pending",
            repair=BehaviorRepairProgress(1, "repair", regression=RegressionState("pending", ("pytest", "-q"))),
        ),
        candidate_chain_revision="repair",
        regression=RegressionState("pending", ("pytest", "-q")),
    )
    store, gateway, runtime = Store(), Gateway(), Runtime()
    candidates = CandidateRepository(tmp_path, {"repair": "class Widget:\n    pass\n"})
    service = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, DeterministicRegressionService(runtime))
    )

    outcome = await service.repair(request(tmp_path, state))

    assert outcome.status == "behavior_repair_regression_clear"
    assert gateway.units == []
    assert outcome.state.behavior_review.repair.attempts == 1


@pytest.mark.asyncio
async def test_behavior_repair_submission_regression_and_promotion_are_isolated(tmp_path):
    store, gateway, runtime = Store(), Gateway(), Runtime()
    candidates = CandidateRepository(tmp_path, {"repair": "class Widget:\n    pass\n"})
    service = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, DeterministicRegressionService(runtime))
    )

    submitted = await service.submit(request(tmp_path, reviewed_state()))

    assert submitted.status == "behavior_repair_submitted"
    assert len(gateway.units) == 1
    assert runtime.requests == []

    regressed = service.run_regression(request(tmp_path, submitted.state))

    assert regressed.status == "behavior_repair_regression_clear"
    assert len(gateway.units) == 1
    assert runtime.requests
    runtime_count = len(runtime.requests)

    promoted = service.promote(request(tmp_path, regressed.state))

    assert promoted.status == "behavior_repair_promoted"
    assert len(gateway.units) == 1
    assert len(runtime.requests) == runtime_count
