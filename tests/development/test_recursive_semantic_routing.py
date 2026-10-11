"""Architectural contract: one semantic return path, no failure-specific rescue engine."""
from dataclasses import replace
import json

import pytest

from core.development.behavior_contract_coordinator import BehaviorContractPlanner
from core.development.strict_tdd_transitions import (
    FeatureTransitionKind, MicrocycleTransitionKind, ScenarioTransitionKind,
)
from tests.development.test_behavior_replanning import ReplanGateway, exhausted
from tests.development.test_strict_tdd_feature_application import contract, request, service


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,kind", [
    ("developer_attempts_exhausted", MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED),
    ("behavior_repair_attempts_exhausted", MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED),
    ("regression_repair_attempts_exhausted", MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED),
    ("Review requires a smaller behavioral frontier", MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED),
])
async def test_all_post_red_semantic_failures_return_to_same_planner(tmp_path, reason, kind):
    app, _, _, scenarios, _ = service(tmp_path, contract("feature"))
    for _ in range(4):
        await app.advance(request())
    gateway = ReplanGateway()
    app.contract_planner = BehaviorContractPlanner(gateway)
    original = scenarios.advance

    async def failed(selected):
        advanced = await original(selected)
        draft = replace(exhausted(selected.behavior, selected.canonical_development_base), status="approved")
        outcome = replace(advanced.result, scenario_id=selected.selected_scenario_id,
                          status=kind.value, canonical_development_base=selected.canonical_development_base,
                          blocked_reason=reason, draft_state=draft,
                          evidence_refs=("accepted-red:frontier-1", "attempts:1-4"))
        return replace(advanced, kind=ScenarioTransitionKind.MICROCYCLE_ADVANCED,
                       microcycle_kind=kind, result=outcome, blocker_or_replan_reason=reason)

    scenarios.advance = failed
    returned = await app.advance(request())
    assert returned.kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED
    assert app.states.load("feature").status == "running"
    await app.advance(request())
    assert len(gateway.requests) == 1
    payload = json.loads(gateway.requests[0].prompt)["request"]
    assert payload["parent"]["ref"] == "B-0"
    assert payload["failure_evidence"] == ["accepted-red:frontier-1", "attempts:1-4"]
    assert "tester_failures" not in payload
    assert "completed_requirements" not in payload
    assert "Widget grows." not in gateway.requests[0].prompt  # unrelated whole source


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses", [
    ["wrong_behavior"] * 4, ["candidate_invalid"] * 4, ["worker_model_timeout"] * 4,
])
async def test_tester_exhaustion_has_no_requirement_replacement_detour(tmp_path, statuses):
    app, _, _, scenarios, _ = service(tmp_path, contract("feature"))
    for _ in range(4):
        await app.advance(request())
    original = scenarios.advance

    async def failed(selected):
        advanced = await original(selected)
        draft = exhausted(selected.behavior, selected.canonical_development_base, statuses=statuses)
        return replace(advanced, result=replace(advanced.result,
                       scenario_id=selected.selected_scenario_id, status="attempts_exhausted",
                       canonical_development_base=selected.canonical_development_base, draft_state=draft))
    scenarios.advance = failed
    result = await app.advance(request())
    assert result.kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED
    assert len(app.states.load("feature").behavior_replans) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [
    "scenario_harness_failure", "intent_protocol_failure", "immutable_test_modified",
    "write_outside_allowed_paths", "revision_mismatch",
])
async def test_nonsemantic_failure_does_not_atomise(tmp_path, reason):
    app, _, _, scenarios, _ = service(tmp_path, contract("feature"))
    for _ in range(4):
        await app.advance(request())
    original = scenarios.advance

    async def failed(selected):
        advanced = await original(selected)
        return replace(advanced, result=replace(advanced.result,
                       status="blocked", blocked_reason=reason))
    scenarios.advance = failed
    result = await app.advance(request())
    assert result.kind == FeatureTransitionKind.BLOCKED
    assert app.states.load("feature").behavior_replans == ()


@pytest.mark.asyncio
async def test_gatekeeper_missing_behavior_returns_to_same_planner(tmp_path):
    planned = contract("feature")
    # Real source grounding, unlike the convenience fixture's shorthand clauses.
    planned = replace(planned, requirement_source="Widget grows.",
                      source_clauses=[replace(planned.source_clauses[0], text="Widget grows.")])
    app, _, _, _, reconciler = service(tmp_path, planned)
    for _ in range(6):
        await app.advance(request())
    gateway = ReplanGateway()
    app.contract_planner = BehaviorContractPlanner(gateway)

    async def missing(_):
        return ({"checklist_ref": "CHK-1", "answer": "NO", "policy": "behavioral",
                 "rationale": "The accepted test does not demonstrate the specified growth."},)
    reconciler.reconcile = missing
    result = await app.advance(request())
    assert result.kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED
    saved = app.states.load("feature")
    assert len(saved.completed_behaviors) == 1
    assert saved.behavior_replans[-1].request.source_clauses[0].text == "Widget grows."
    await app.advance(request())
    assert len(gateway.requests) == 1
    assert "signature" not in saved.behavior_replans[-1].request.parent.ref.lower()

@pytest.mark.asyncio
@pytest.mark.parametrize("status,paths,kind", [
    ("backend_unavailable", [], "infrastructure"),
    ("capability_unavailable", [], "infrastructure"),
    ("checks_passed", ["tests/test_widget.py"], "mechanical_authority"),
    ("checks_passed", ["../outside.txt"], "mechanical_authority"),
    ("malformed_result", [], "protocol"),
])
async def test_actual_developer_boundary_does_not_consume_semantic_attempt(tmp_path, status, paths, kind):
    from core.development.strict_microcycle import StrictMicrocycleService, StrictMicrocycleDependencies, DeveloperExecutionContext
    from core.development.python_pytest_adapter import PythonPytestAdapter
    from core.development.python_test_material import PythonTestMaterial
    from core.development.strict_microcycle import DeveloperFrontierWorkUnitFactory, RegressionRepairWorkUnitFactory
    from core.development.microcycle_domain import BoundaryAssessment, BoundaryDiagnostic
    from core.execution.work_execution_boundary import ExecutionBoundaryFailure
    from core.execution.work_unit_gateway import WorkUnitExecutionResult, ExecutionPolicyEvidence
    from tests.development.test_strict_microcycle import MemoryStore, CandidateRepository, initial_state, request as micro_request, regression
    class Gateway:
        async def execute(self, unit, binding):
            return WorkUnitExecutionResult(unit.id, True, status, accepted_revision="untrusted",
                policy_evidence=ExecutionPolicyEvidence(unit.allowed_paths, paths))
    store = MemoryStore()
    state = initial_state()
    state = replace(state, current_accepted_red_revision="red",
        boundary_evidence=(BoundaryAssessment("valid_behavioral_red", state.frontier.active_fragment_id,
                                               BoundaryDiagnostic("assertion_failure", "RED")),))
    store.save(state)
    service = StrictMicrocycleService(StrictMicrocycleDependencies(store,
        CandidateRepository(tmp_path, {"base": ""}), Gateway(),
        type("Catalog", (), {"for_language": lambda self, _: PythonPytestAdapter()})(), regression(),
        developer_factory=DeveloperFrontierWorkUnitFactory(PythonTestMaterial()),
        regression_repair_factory=RegressionRepairWorkUnitFactory(PythonTestMaterial())))
    with pytest.raises(ExecutionBoundaryFailure) as error:
        await service._developer(DeveloperExecutionContext(micro_request(tmp_path, state), state))
    assert error.value.kind.value == kind
    assert store.load(state.scenario_draft.scenario_id) == state
    assert not state.developer_attempts


@pytest.mark.asyncio
async def test_legacy_unsplittable_is_protocol_failure_not_atomicity(tmp_path):
    from tests.development.test_behavior_replanning import pending_application
    from core.development.behavior_replan_domain import BehaviorReplanPhase
    invalid = {"disposition": "unsplittable", "rationale": "I think this is atomic."}
    app, gateway, _, _, _, _ = await pending_application(tmp_path, [invalid, invalid])
    await app.run(request())
    record = app.states.load("feature").behavior_replans[-1]
    assert record.phase == BehaviorReplanPhase.FAILED
    assert record.blocker.value == "behavior_replan_protocol_failure"
    assert record.correction_attempted and len(gateway.requests) == 2


@pytest.mark.asyncio
async def test_source_authority_insufficiency_is_reported_without_atomic_claim(tmp_path):
    from tests.development.test_behavior_replanning import pending_application
    payload = {"disposition": "source_authority_insufficient", "rationale": "No grounded child proposal.", "coverage_rationale": "", "children": []}
    app, _, _, _, _, _ = await pending_application(tmp_path, payload)
    await app.run(request())
    record = app.states.load("feature").behavior_replans[-1]
    assert record.blocker.value == "behavior_source_authority_insufficient"
    assert "atomicity is unproven" in record.detail


def test_test_material_capability_is_language_neutral():
    from core.development.test_material import TestSourceRequest
    from core.development.specification_reconciliation import GitAcceptedTestCatalog, TestCatalogRevision
    from pathlib import Path
    class Material:
        def test_path(self, identity): return "spec/example.any"
        def extract(self, request): return "generic accepted test"
    catalog = GitAcceptedTestCatalog(Path("."), TestCatalogRevision("rev", Material()))
    assert catalog.test_material.test_path("opaque test identity") == "spec/example.any"
    assert catalog.test_material.extract(TestSourceRequest("opaque", "opaque")) == "generic accepted test"
