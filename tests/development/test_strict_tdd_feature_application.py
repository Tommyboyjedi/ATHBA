from dataclasses import replace

import pytest

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.project_environment import ProjectEnvironmentService
from core.development.specification_domain import (
    SourceRequirementClause,
    SpecificationChecklist,
    SpecificationChecklistItem,
    SpecificationGatekeeperRunState,
)
from core.development.strict_tdd_feature_application import (
    FeatureScenarioResult,
    StrictTddFeatureApplicationService,
    StrictTddFeatureDependencies,
)
from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest
from core.development.strict_tdd_transitions import (
    MicrocycleTransitionKind,
    ScenarioAdvanceResult,
    ScenarioTransitionKind,
    TransitionFingerprint,
)
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository


def request(project_id="feature"):
    return StrictTddFeatureRequest(
        project_id, "Widget grows.", "python", "pytest", ("widget.py",),
        ("tests/test_widget.py",), "python-test", "resume", None, "evidence",
    )


def contract(project_id, count=1):
    clauses = [SourceRequirementClause(f"SRC-{index}", f"behavior {index}", "behavior") for index in range(count)]
    requirements = [
        BehaviorContractRequirement(
            f"B-{index}", [f"SRC-{index}"], f"behavior {index}", "observable result",
            "test hint",
        )
        for index in range(count)
    ]
    return BehaviorContract(
        f"contract-{project_id}", project_id, "Widget", "grow", "Widget grows.",
        clauses, requirements, [], ["widget.py"], ["tests/test_widget.py"],
    )


class Planner:
    def __init__(self, value):
        self.value = value
        self.requests = []

    async def create_contract(self, value):
        self.requests.append(value)
        return self.value


class Gatekeeper:
    def __init__(self):
        self.requests = []

    async def ensure_state(self, value):
        self.requests.append(value)
        item = SpecificationChecklistItem("CHK-1", "Widget grows.", "behavior")
        return SpecificationGatekeeperRunState(SpecificationChecklist(value.contract.project_id, value.contract.requirement_source, [item]))


class Scenarios:
    def __init__(self):
        self.requests = []

    async def execute(self, value):
        self.requests.append(value)
        return FeatureScenarioResult(
            value.behavior.ref, f"scenario-{value.behavior.ref}", "behavior_complete",
            "refs/heads/main", f"sha-{value.behavior.ref}", None, None,
            ("review-approved",),
        )

    async def advance(self, value):
        outcome = await self.execute(value)
        return ScenarioAdvanceResult(
            ScenarioTransitionKind.SCENARIO_COMPLETED,
            "scenario_complete",
            "behavior_complete",
            outcome.behavior_ref,
            outcome.scenario_id,
            outcome.canonical_ref,
            outcome.canonical_development_base,
            outcome.working_ref,
            outcome.working_revision,
            outcome.evidence_refs,
            False,
            False,
            False,
            None,
            TransitionFingerprint(
                "behavior_complete",
                outcome.behavior_ref,
                outcome.scenario_id,
                None,
                outcome.canonical_development_base,
                None,
                (),
                "complete",
            ),
            outcome,
        )


class Reconciler:
    def __init__(self):
        self.calls = []

    async def reconcile(self, request):
        self.calls.append(request)
        return ({"checklist_ref": "CHK-1", "answer": "YES"},)


def service(tmp_path, planned):
    environment = ProjectEnvironmentService(tmp_path / "projects", python_executable="/srv/ATHBA/.venv/bin/python")
    planner, gatekeeper, scenarios, reconciler = Planner(planned), Gatekeeper(), Scenarios(), Reconciler()
    application = StrictTddFeatureApplicationService(
        StrictTddFeatureDependencies(
            environment, StrictTddFeatureRepository(tmp_path / "features"),
            planner, gatekeeper, scenarios, reconciler,
        )
    )
    return application, planner, gatekeeper, scenarios, reconciler


@pytest.mark.asyncio
async def test_one_behavior_feature_completes_and_restart_uses_persisted_state(tmp_path):
    application, planner, gatekeeper, scenarios, reconciler = service(tmp_path, contract("feature"))
    first = await application.run(request())

    assert first.current_status == "completed"
    assert [item.behavior_ref for item in first.completed_behaviors] == ["B-0"]
    assert len(planner.requests) == len(gatekeeper.requests) == len(scenarios.requests) == len(reconciler.calls) == 1
    resumed = await application.run(request())
    assert resumed == first
    assert len(planner.requests) == len(gatekeeper.requests) == len(scenarios.requests) == len(reconciler.calls) == 1


@pytest.mark.asyncio
async def test_multi_behavior_starts_second_only_after_first_completed_base(tmp_path):
    application, _planner, _gatekeeper, scenarios, reconciler = service(tmp_path, contract("feature", 2))
    result = await application.run(request())

    assert result.current_status == "completed"
    assert [item.behavior.ref for item in scenarios.requests] == ["B-0", "B-1"]
    assert scenarios.requests[1].canonical_development_base == "sha-B-0"
    assert len(reconciler.calls[0].completed_behaviors) == 2
    assert reconciler.calls[0].canonical_revision == "sha-B-1"


@pytest.mark.asyncio
async def test_rejected_or_unresolved_behavior_blocks_before_reconciliation(tmp_path):
    application, _planner, _gatekeeper, scenarios, reconciler = service(tmp_path, contract("feature"))
    original = scenarios.execute

    async def blocked(value):
        result = await original(value)
        return replace(result, status="replan_required", blocked_reason="semantic replan")

    scenarios.execute = blocked
    result = await application.run(request())

    assert result.current_status == "blocked"
    assert result.blocked_reason == "semantic replan"
    assert reconciler.calls == []


@pytest.mark.asyncio
async def test_same_requirement_is_independently_supplied_to_planner_and_gatekeeper(tmp_path):
    application, planner, gatekeeper, _scenarios, _reconciler = service(tmp_path, contract("feature"))
    await application.run(request())

    assert planner.requests[0].requirement_text == "Widget grows."
    assert gatekeeper.requests[0].contract.requirement_source == "Widget grows."
    assert not hasattr(planner.requests[0], "checklist")


@pytest.mark.asyncio
async def test_scenario_completion_and_behavior_recording_are_separate_advances(tmp_path):
    application, _planner, _gatekeeper, scenarios, _reconciler = service(tmp_path, contract("feature"))
    transitions = []

    for _ in range(6):
        transitions.append(await application.advance(request()))

    scenario = next(item for item in transitions if item.kind.value == "scenario_advanced")
    recorded = next(item for item in transitions if item.kind.value == "behavior_recorded")
    assert scenario.result.completed_behaviors == ()
    assert scenario.transition_path is not None
    assert scenario.transition_path.scenario_kind == ScenarioTransitionKind.SCENARIO_COMPLETED
    assert recorded.transition_path is not None
    assert recorded.transition_path.scenario_kind is None
    assert not recorded.external_reasoning_invoked
    assert not recorded.rack_ai_invoked
    assert not recorded.deterministic_regression_invoked
    assert len(recorded.result.completed_behaviors) == 1
    assert len(scenarios.requests) == 1


@pytest.mark.asyncio
async def test_nested_microcycle_kind_and_effect_flags_are_forwarded_without_recovery(tmp_path):
    application, _planner, _gatekeeper, scenarios, _reconciler = service(tmp_path, contract("feature"))

    async def nested(value):
        outcome = FeatureScenarioResult(
            value.behavior.ref, f"scenario-{value.behavior.ref}", "green_verified",
            "refs/heads/main", "a" * 40, "refs/heads/work", "b" * 40, ("evidence://green",),
        )
        return ScenarioAdvanceResult(
            ScenarioTransitionKind.MICROCYCLE_ADVANCED, "frontier_red", "green_verified",
            outcome.behavior_ref, outcome.scenario_id, outcome.canonical_ref,
            outcome.canonical_development_base, outcome.working_ref, outcome.working_revision,
            outcome.evidence_refs, True, True, True, None,
            TransitionFingerprint("green_verified", outcome.behavior_ref, outcome.scenario_id, 0, "a" * 40, "b" * 40, (), "regression"),
            outcome, MicrocycleTransitionKind.REGRESSION_CLEAR, True, "c" * 40,
        )

    scenarios.advance = nested
    for _ in range(4):
        await application.advance(request())
    advanced = await application.advance(request())

    assert advanced.transition_path is not None
    assert advanced.transition_path.scenario_kind == ScenarioTransitionKind.MICROCYCLE_ADVANCED
    assert advanced.transition_path.microcycle_kind == MicrocycleTransitionKind.REGRESSION_CLEAR
    assert advanced.external_reasoning_invoked
    assert advanced.rack_ai_invoked
    assert advanced.deterministic_regression_invoked
    assert advanced.candidate_revision == "c" * 40
