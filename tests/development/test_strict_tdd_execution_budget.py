import pytest

from core.development.scenario_drafting import (
    ScenarioDraftWorkUnitFactory,
    ScenarioDraftWorkUnitRequest,
)
from core.development.scenario_drafting_domain import (
    ScenarioDraftAttempt,
    ScenarioDraftRequest,
    ScenarioRepositoryFacts,
)
from core.development.strict_tdd_execution_budget import (
    StrictTddExecutionBudgetPolicy,
    StrictTddExecutionBudgets,
    StrictTddWorkKind,
)
from core.development.tdd_progression import TddStepProposal
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding, to_rack_ai_request


def _request() -> ScenarioDraftRequest:
    ticket = TddStepProposal(
        "budget-ticket",
        ["SRC-BUDGET"],
        "Budget behavior.",
        "tests/test_budget.py::test_budget",
        "Budget behavior is observable.",
        "tests/test_budget.py",
        "budget.py",
        "unused",
        "unused",
        "Budget behavior is observable.",
    )
    return ScenarioDraftRequest(
        "budget-scenario",
        ticket,
        ("SRC-BUDGET",),
        "python",
        "pytest",
        ticket.test_path,
        ScenarioRepositoryFacts("a" * 40, ("budget.py", ticket.test_path), "", ""),
        "a" * 40,
    )


def test_production_policy_uses_only_typed_work_kind_defaults():
    policy = StrictTddExecutionBudgetPolicy()
    assert {kind: policy.timeout_for(kind) for kind in StrictTddWorkKind} == {
        StrictTddWorkKind.SCENARIO_DRAFT: 300,
        StrictTddWorkKind.SCENARIO_REPAIR: 300,
        StrictTddWorkKind.FRONTIER_DEVELOPER: 300,
        StrictTddWorkKind.REGRESSION_REPAIR: 450,
        StrictTddWorkKind.BEHAVIOR_REPAIR: 600,
        StrictTddWorkKind.GENERIC: 900,
    }


def test_scenario_factory_selects_draft_then_repair_budget_and_rack_request():
    factory = ScenarioDraftWorkUnitFactory()
    first = factory.build(ScenarioDraftWorkUnitRequest(_request(), 1, None))
    repair = factory.build(
        ScenarioDraftWorkUnitRequest(
            _request(),
            2,
            "remove the invalid form",
            ScenarioDraftAttempt(1, "budget-ticket--scenario-draft-1", None, "b" * 40, "evidence/1", "candidate_invalid"),
        )
    )
    assert (first.work_kind, first.timeout_seconds) == (StrictTddWorkKind.SCENARIO_DRAFT, 300)
    assert (repair.work_kind, repair.timeout_seconds) == (StrictTddWorkKind.SCENARIO_REPAIR, 300)
    payload = to_rack_ai_request(
        "budget-workload",
        RepositoryBinding("budget-repository", "main", "a" * 40),
        first,
    )
    assert payload["limits"]["timeout_seconds"] == 300


def test_generic_work_unit_retains_900_second_fallback():
    unit = DevelopmentWorkUnit(
        "generic", "project", "ticket", "generic work", ["generic.py"],
        AcceptanceContract([["python3", "-m", "pytest", "tests/test_generic.py"]]),
        status=WorkUnitStatus.READY,
    )
    assert unit.work_kind == StrictTddWorkKind.GENERIC
    assert unit.timeout_seconds == 900


@pytest.mark.parametrize(
    "values",
    [
        {"scenario_draft_seconds": 0},
        {"scenario_repair_seconds": -1},
        {"frontier_developer_seconds": 901},
    ],
)
def test_policy_rejects_invalid_typed_budget_values(values):
    with pytest.raises(ValueError):
        StrictTddExecutionBudgets(**values)


def test_persisted_attempt_budget_metadata_is_optional_for_old_records():
    old = ScenarioDraftAttempt.from_dict(
        {"attempt_number": 1, "work_unit_id": "draft-1", "change_id": None,
         "candidate_revision": None, "evidence_location": None,
         "status": "candidate_rejected"}
    )
    current = ScenarioDraftAttempt(
        1, "draft-1", None, None, None, "candidate_rejected",
        work_kind="scenario_draft", timeout_seconds=300,
    )
    assert (old.work_kind, old.timeout_seconds) == (None, None)
    restored = ScenarioDraftAttempt.from_dict(current.to_dict())
    assert restored.timeout_seconds == 300
