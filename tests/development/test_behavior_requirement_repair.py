"""Deterministic malformed-requirement replacement and durable lifecycle proofs."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.behavior_contract_coordinator import BehaviorContractPlanner
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.behavior_requirement_repair_domain import BehaviorRepairBlocker, BehaviorRepairPhase
from core.development.microcycle_domain import ScenarioIntentResult
from core.development.scenario_drafting_domain import ScenarioDraftAttempt, ScenarioDraftRunState
from core.development.specification_domain import SourceRequirementClause
from core.development.strict_tdd_feature_application import (
    FeatureScenarioRequest, StrictTddFeatureApplicationService, StrictTddFeatureDependencies,
)
from core.development.strict_tdd_feature_domain import CompletedBehaviorReference, StrictTddFeatureState
from core.development.strict_tdd_feature_execution import StrictFeatureScenarioDependencies, StrictFeatureScenarioExecutor
from core.development.strict_tdd_feature_requirement_repair import require_repair
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_transitions import FeatureTransitionKind, MicrocycleTransitionKind, ScenarioTransitionKind
from core.execution.reasoning_gateway import ReasoningResult
from core.execution.work_unit_gateway import WorkUnitExecutionResult
from tests.development.test_scenario_drafting import components
from tests.development.test_strict_tdd_feature_application import contract, request, service

SOURCE = "The SignalBoard shall provide a mechanism to retrieve the latest payload for a given signal name."
RATIONALES = (
    "The ticket describes a non-existent signal, but the submitted test performs normal publish/retrieve behavior.",
    "The source requires normal latest-payload retrieval; the behavior introduced unsupported non-existent-signal semantics.",
)


def fixture_contract():
    planned = contract("feature", 3)
    parent = BehaviorContractRequirement(
        "REQ-006", ["REQ-006"], "Query non-existent signal", "Retrieval of non-existent signal",
        "Request a name that was never published and verify the error/null response",
        "Return None or raise KeyError", True, [planned.observable_requirements[0].ref],
    )
    return replace(planned, requirement_source="FULL ORIGINAL FEATURE REQUIREMENT MUST NOT LEAK",
                   source_clauses=[planned.source_clauses[0], SourceRequirementClause("REQ-006", SOURCE, "behavior"),
                                   planned.source_clauses[2]],
                   observable_requirements=[planned.observable_requirements[0], parent, planned.observable_requirements[2]])


def repair_payload():
    return dict(summary="Retrieve latest published payload",
                observable_outcome="Retrieve the latest published payload for a named signal",
                test_hint="Publish successive payloads and retrieve the latest for the named signal",
                error_expectation=None, preserves_state_on_failure=True,
                rationale="Remove the unsupported missing-signal assumption and express the source retrieval mechanism.")


def exhausted(state, statuses=("wrong_behavior", "wrong_behavior", "worker_model_timeout", "worker_model_timeout")):
    parent = BehaviorContract.from_dict(state.contract_payload).observable_requirements[1]
    attempts = tuple(ScenarioDraftAttempt(
        index, f"work-{index}", None, "candidate" if status == "wrong_behavior" else None, f"evidence/{index}",
        "semantic_repair_required" if status == "wrong_behavior" else "timed_out_no_candidate",
        "General candidate feedback must not leak",
        intent=ScenarioIntentResult(state.current_scenario_id, status, RATIONALES[(index - 1) % 2])
        if status == "wrong_behavior" else None,
        candidate_source="TEST SOURCE MUST NOT LEAK" if status == "wrong_behavior" else None,
        no_candidate_outcome=None if status == "wrong_behavior" else status,
    ) for index, status in enumerate(statuses, 1))
    return ScenarioDraftRunState(state.current_scenario_id, parent.ref, tuple(parent.source_refs),
                                 "python", "pytest", "tests/test_widget.py", state.canonical_development_base,
                                 attempts, status="attempts_exhausted")


class RepairGateway:
    def __init__(self, payload=None):
        self.payload = repair_payload() if payload is None else payload
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        assert request.purpose == "athba_behavior_requirement_repair"
        if isinstance(self.payload, BaseException):
            raise self.payload
        return ReasoningResult(self.payload if isinstance(self.payload, str) else json.dumps(self.payload))


async def setup(tmp_path, payload=None):
    planned = fixture_contract()
    app, _, _, scenarios, _ = service(tmp_path, planned)
    for _ in range(3):
        await app.advance(request())
    state = app.states.load("feature")
    state = replace(state, current_scenario_id="feature--REQ-006",
                    completed_behaviors=(CompletedBehaviorReference("B-0", "feature--B-0",
                                         state.canonical_development_base, ("prior-regression-proof",)),))
    app.states.save(state)
    gateway = RepairGateway(payload)
    app.contract_planner = BehaviorContractPlanner(gateway)
    store = ScenarioDraftStateRepo(tmp_path / "drafts")
    draft = exhausted(state)
    store.save(draft)
    original = scenarios.advance

    async def advance(value):
        prior = await original(value)
        return replace(prior, result=replace(prior.result, scenario_id=value.scenario_id,
                       status="attempts_exhausted", canonical_development_base=value.canonical_development_base,
                       draft_state=store.load(value.scenario_id)),
                       kind=ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED)
    scenarios.advance = advance
    return app, gateway, store, state


def restart(app, tmp_path):
    return StrictTddFeatureApplicationService(StrictTddFeatureDependencies(
        app.environment, StrictTddFeatureRepository(tmp_path / "features"), app.contract_planner,
        app.gatekeeper, app.scenarios, app.reconciler,
    ))


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses,eligible", [
    (("wrong_behavior",) * 4, True),
    (("wrong_behavior", "wrong_behavior", "worker_model_timeout", "worker_model_timeout"), True),
    (("worker_model_timeout",) * 4, False),
    (("model_completed_without_candidate",) * 4, False),
])
async def test_eligibility_from_typed_intent_only(tmp_path, statuses, eligible):
    app, gateway, store, state = await setup(tmp_path)
    store.save(exhausted(state, statuses))
    result = await app.advance(request())
    assert (result.kind == FeatureTransitionKind.BEHAVIOR_REPAIR_REQUIRED) == eligible
    assert bool(app.states.load("feature").behavior_repairs) == eligible
    assert gateway.requests == []


@pytest.mark.asyncio
async def test_status_or_feedback_alone_is_not_semantic_evidence(tmp_path):
    _, _, _, state = await setup(tmp_path)
    draft = exhausted(state)
    spoofed = replace(draft, attempts=tuple(replace(item, intent=None, status="wrong_behavior") for item in draft.attempts))
    assert require_repair(state, spoofed) is None
    foreign = replace(draft, attempts=tuple(replace(item, intent=replace(item.intent, scenario_id="other"))
                                           if item.intent else item for item in draft.attempts))
    assert require_repair(state, foreign) is None
    assert require_repair(state, replace(draft, status="drafting")) is None


@pytest.mark.asyncio
async def test_developer_exhaustion_skips_repair_even_with_wrong_behavior_history(tmp_path):
    app, gateway, store, state = await setup(tmp_path)
    original = app.scenarios.advance

    async def advance(value):
        result = await original(value)
        return replace(result, kind=ScenarioTransitionKind.MICROCYCLE_ADVANCED,
                       microcycle_kind=MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED,
                       blocker_or_replan_reason="developer_attempts_exhausted")
    app.scenarios.advance = advance
    assert (await app.advance(request())).kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED
    assert not app.states.load("feature").behavior_repairs
    assert not gateway.requests


@pytest.mark.asyncio
async def test_minimal_packet_replacement_and_restart_preserve_every_other_field(tmp_path):
    app, gateway, store, before = await setup(tmp_path)
    old_path = next((tmp_path / "drafts").glob("*.json"))
    old_bytes = old_path.read_bytes()
    required = await app.advance(request())
    assert required.fingerprint.pending_action == "behavior_repair_required"
    app = restart(app, tmp_path)
    received = await app.advance(request())
    assert received.kind == FeatureTransitionKind.BEHAVIOR_REPAIR_RECEIVED
    persisted = app.states.load("feature")
    assert persisted.behavior_repairs[0].raw_response == json.dumps(repair_payload())
    assert persisted.behavior_repairs[0].phase == BehaviorRepairPhase.RECEIVED
    sent = gateway.requests[0]
    packet = json.loads(sent.prompt)
    original = fixture_contract().observable_requirements[1]
    assert packet["behavior"] == original.to_dict()
    assert packet["source_clauses"] == [fixture_contract().source_clauses[1].to_dict()]
    assert packet["intent_review_feedback"] == [
        dict(attempt_number=i, status="wrong_behavior", rationale=r) for i, r in enumerate(RATIONALES, 1)]
    assert set(packet) == {"instruction", "behavior", "source_clauses", "intent_review_feedback", "response_schema"}
    for forbidden in (fixture_contract().requirement_source, "behavior 0", "behavior 2",
                      "TEST SOURCE MUST NOT LEAK", "General candidate feedback", "production_source", "completed_requirements"):
        assert forbidden not in sent.prompt
    assert sent.project_id == "feature"
    app = restart(app, tmp_path)
    applied = await app.advance(request())
    assert applied.kind == FeatureTransitionKind.BEHAVIOR_REPAIR_APPLIED
    after = app.states.load("feature")
    updated = BehaviorContract.from_dict(after.contract_payload)
    expected = replace(original, **{k: v for k, v in repair_payload().items() if k != "rationale"})
    assert updated == replace(fixture_contract(), observable_requirements=[
        fixture_contract().observable_requirements[0], expected, fixture_contract().observable_requirements[2]])
    assert after.behavior_repairs[0].repaired == expected
    assert after.behavior_repairs[0].rationale == repair_payload()["rationale"]
    assert after.completed_behaviors == before.completed_behaviors
    assert after.canonical_development_base == before.canonical_development_base
    assert after.canonical_ref == before.canonical_ref
    assert after.gatekeeper_payload == before.gatekeeper_payload
    assert old_path.read_bytes() == old_bytes
    assert len(store.load("feature--REQ-006").attempts) == 4
    assert StrictTddFeatureState.from_dict(after.to_dict()) == after
    app = restart(app, tmp_path)
    selected = await app.advance(request())
    assert selected.scenario_id == "feature--repair-1--REQ-006"
    assert len(gateway.requests) == 1
    for transition in (required, received, applied):
        from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleRunContext
        from core.development.strict_tdd_transition_provenance import StrictTddTransitionEventProjector, StrictTddTransitionProjectionRequest
        event = StrictTddTransitionEventProjector().project(StrictTddTransitionProjectionRequest(
            StrictTddLifecycleRunContext("run", "feature", "SignalBoard", "head", "fake"), transition, 1))
        assert event[0].event_kind.value == transition.kind.value


@pytest.mark.asyncio
async def test_actual_executor_uses_fresh_persisted_budget_and_preserves_old_attempts(tmp_path):
    app, gateway, store, before = await setup(tmp_path)
    for _ in range(4):
        await app.advance(request())
    old = (tmp_path / "drafts" / "feature--REQ-006.json").read_bytes()
    drafting, worker, _, _ = components(
        [WorkUnitExecutionResult(f"timeout-{i}", False, "timeout", selected_worker_id="fake") for i in range(4)],
        [], {}, store)
    app.scenarios = StrictFeatureScenarioExecutor(StrictFeatureScenarioDependencies(drafting, None, None, app.environment))
    for index in range(1, 5):
        await app.advance(request())
        fresh = store.load("feature--repair-1--REQ-006")
        assert fresh.behavior_ref == "REQ-006" and len(fresh.attempts) == index
        assert fresh.attempts[-1].attempt_number == index
        app = restart(app, tmp_path)
    await app.advance(request())
    assert len(worker.calls) == 4
    assert len(gateway.requests) == 1
    assert store.load("feature--repair-1--REQ-006").status == "attempts_exhausted"
    assert (tmp_path / "drafts" / "feature--REQ-006.json").read_bytes() == old
    assert app.states.load("feature").completed_behaviors == before.completed_behaviors
    assert all(binding.base_sha == before.canonical_development_base for _, binding in worker.calls)


@pytest.mark.asyncio
async def test_second_semantic_exhaustion_reaches_existing_replan_without_repeat_repair(tmp_path):
    app, gateway, store, before = await setup(tmp_path)
    for _ in range(4):
        await app.advance(request())
    state = app.states.load("feature")
    store.save(exhausted(state))
    assert (await app.advance(request())).kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED
    after = app.states.load("feature")
    assert len(after.behavior_repairs) == 1 and len(after.behavior_replans) == 1
    assert after.behavior_replans[0].request.parent == after.behavior_repairs[0].repaired
    assert after.behavior_replans[0].request.tester_failures.scenario_id == "feature--repair-1--REQ-006"
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid,blocker", [
    ("not json", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("fenced", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("identity", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("missing", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("empty", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("error", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("boolean", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("duplicate", BehaviorRepairBlocker.PROTOCOL_FAILURE),
    ("same", BehaviorRepairBlocker.NO_PROGRESS),
    ("provider", BehaviorRepairBlocker.PROVIDER_FAILURE),
])
async def test_invalid_repairs_fail_closed_with_durable_raw_evidence(tmp_path, invalid, blocker):
    payload = repair_payload()
    if invalid == "not json":
        payload = invalid
    elif invalid == "fenced":
        payload = "```json\n" + json.dumps(payload) + "\n```"
    elif invalid == "identity":
        payload["ref"] = "NEW"
    elif invalid == "missing":
        del payload["summary"]
    elif invalid == "empty":
        payload["summary"] = " "
    elif invalid == "error":
        payload["error_expectation"] = ""
    elif invalid == "boolean":
        payload["preserves_state_on_failure"] = "true"
    elif invalid == "duplicate":
        payload = json.dumps(payload)[:-1] + ', "summary": "other"}'
    elif invalid == "same":
        payload = {key: value for key, value in fixture_contract().observable_requirements[1].to_dict().items()
                   if key not in {"ref", "source_refs", "depends_on"}}
        payload["rationale"] = "No change"
    else:
        payload = RuntimeError("provider failed")
    app, gateway, store, before = await setup(tmp_path, payload)
    result = await app.run(request())
    assert result.blocked_reason == blocker.value
    record = app.states.load("feature").behavior_repairs[0]
    assert record.phase == BehaviorRepairPhase.FAILED and record.blocker == blocker
    assert record.detail and record.repaired is None
    assert app.states.load("feature").contract_payload == before.contract_payload
    if invalid != "provider":
        assert record.raw_response == (payload if isinstance(payload, str) else json.dumps(payload))
    assert (await restart(app, tmp_path).run(request())) == result
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_process_interruption_after_submission_never_repeats_request(tmp_path):
    class ProcessDeath(BaseException):
        pass
    app, gateway, store, before = await setup(tmp_path, ProcessDeath())
    await app.advance(request())
    with pytest.raises(ProcessDeath):
        await app.advance(request())
    assert app.states.load("feature").behavior_repairs[0].phase == BehaviorRepairPhase.STARTED
    result = await restart(app, tmp_path).run(request())
    assert result.blocked_reason == BehaviorRepairBlocker.INTERRUPTED.value
    assert len(gateway.requests) == 1
    assert app.states.load("feature").contract_payload == before.contract_payload


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["source", "canonical", "parent"])
async def test_received_repair_revalidates_trusted_identity(tmp_path, change):
    app, gateway, _, _ = await setup(tmp_path)
    await app.advance(request())
    await app.advance(request())
    state = app.states.load("feature")
    planned = BehaviorContract.from_dict(state.contract_payload)
    if change == "canonical":
        state = replace(state, canonical_development_base="different")
    elif change == "source":
        planned = replace(planned, source_clauses=[planned.source_clauses[0],
                          replace(planned.source_clauses[1], text="changed"), planned.source_clauses[2]])
        state = replace(state, contract_payload=planned.to_dict())
    else:
        planned = replace(planned, observable_requirements=[planned.observable_requirements[0],
                          replace(planned.observable_requirements[1], summary="changed"),
                          planned.observable_requirements[2]])
        state = replace(state, contract_payload=planned.to_dict())
    app.states.save(state)
    assert (await restart(app, tmp_path).run(request())).blocked_reason == BehaviorRepairBlocker.INCOMPATIBLE.value
    assert len(gateway.requests) == 1


def test_unrepaired_scenario_identity_remains_compatible(tmp_path):
    app, _, _, _, _ = service(tmp_path, fixture_contract())
    project = app.environment.create_or_load_python_project("feature")
    planned = fixture_contract()
    value = FeatureScenarioRequest(project, planned, planned.observable_requirements[1], project.trusted_base_sha)
    assert value.selected_scenario_id == "feature--REQ-006"


@pytest.mark.asyncio
async def test_repaired_behavior_completion_continues_with_prior_regression_nodes(tmp_path):
    from core.development.strict_tdd_feature_execution import canonical_test_node_for
    from tests.development.test_strict_tdd_feature_application import Scenarios
    app, gateway, store, before = await setup(tmp_path)
    for _ in range(3):
        await app.advance(request())
    scenarios = Scenarios()
    original = scenarios.execute

    async def execute(value):
        outcome = await original(value)
        return replace(outcome, scenario_id=value.selected_scenario_id)
    scenarios.execute = execute
    app.scenarios = scenarios
    result = await app.run(request())
    assert result.current_status == "completed"
    repaired_request = scenarios.requests[0]
    assert repaired_request.behavior.ref == "REQ-006"
    assert repaired_request.scenario_id == "feature--repair-1--REQ-006"
    assert repaired_request.canonical_development_base == before.canonical_development_base
    assert repaired_request.prior_completed_test_nodes == (canonical_test_node_for(fixture_contract(), "B-0"),)
    assert result.completed_behaviors[0] == before.completed_behaviors[0]
    assert result.completed_behaviors[1].scenario_id == repaired_request.scenario_id
    assert len(store.load("feature--REQ-006").attempts) == 4
    assert len(gateway.requests) == 1
    assert (await restart(app, tmp_path).run(request())) == result


@pytest.mark.asyncio
async def test_multiple_source_refs_resolve_exactly_in_behavior_order(tmp_path):
    app, gateway, _, state = await setup(tmp_path)
    planned = fixture_contract()
    parent = replace(planned.observable_requirements[1], source_refs=["REQ-006", "SRC-2"])
    planned = replace(planned, observable_requirements=[planned.observable_requirements[0],
                                                       parent, planned.observable_requirements[2]])
    state = replace(state, contract_payload=planned.to_dict())
    required = require_repair(state, exhausted(state))
    app.states.save(required)
    await app.advance(request())
    packet = json.loads(gateway.requests[0].prompt)
    assert packet["source_clauses"] == [planned.source_clauses[1].to_dict(), planned.source_clauses[2].to_dict()]
    assert "behavior 0" not in gateway.requests[0].prompt


@pytest.mark.asyncio
async def test_missing_source_clause_after_receipt_is_typed_incompatible_blocker(tmp_path):
    app, gateway, _, _ = await setup(tmp_path)
    await app.advance(request())
    await app.advance(request())
    state = app.states.load("feature")
    payload = dict(state.contract_payload)
    payload["source_clauses"] = [item for item in payload["source_clauses"] if item["ref"] != "REQ-006"]
    app.states.save(replace(state, contract_payload=payload))
    result = await restart(app, tmp_path).run(request())
    assert result.blocked_reason == BehaviorRepairBlocker.INCOMPATIBLE.value
    assert len(gateway.requests) == 1


def test_split_still_rejects_a_child_reproducing_the_whole_parent():
    from core.development.behavior_replan_domain import BehaviorReplanPhase, BehaviorReplanPolicy
    from core.development.behavior_replan_validation import BehaviorSplitValidationContext, validate_split
    from core.development.behavior_replanning import _parse
    from core.development.strict_tdd_feature_replan import require_replan
    from tests.development.test_behavior_replanning import exhausted as split_exhausted, split_payload
    planned = contract("feature")
    state = StrictTddFeatureState("feature", "hash", "running", planned.to_dict(),
                                 current_scenario_id="feature--B-0", canonical_ref="refs/heads/main",
                                 canonical_development_base="trusted")
    record = require_replan(state, split_exhausted(planned.observable_requirements[0])).behavior_replans[0]
    payload = split_payload(record.request.parent.to_dict())
    payload["children"][0]["observable_outcome"] = record.request.parent.observable_outcome + " with more detail"
    received = replace(record, phase=BehaviorReplanPhase.RECEIVED,
                       response=_parse(json.dumps(payload), record.request))
    with pytest.raises(ValueError, match="child reproduces the entire parent outcome"):
        validate_split(received, BehaviorSplitValidationContext(planned, (), BehaviorReplanPolicy()))


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["received", "started"])
async def test_independent_process_resumes_without_a_repair_planner(tmp_path, phase):
    import subprocess
    import sys
    app, gateway, _, _ = await setup(tmp_path)
    await app.advance(request())
    await app.advance(request())
    if phase == "started":
        state = app.states.load("feature")
        app.states.save(replace(state, behavior_repairs=(
            replace(state.behavior_repairs[0], phase=BehaviorRepairPhase.STARTED, raw_response=None),)))
    program = """
import asyncio
import sys
from pathlib import Path
from tests.development.test_behavior_requirement_repair import fixture_contract
from tests.development.test_strict_tdd_feature_application import service, request
from core.development.strict_tdd_transitions import FeatureTransitionKind

async def main():
    app = service(Path(sys.argv[1]), fixture_contract())[0]
    # This planner only supports initial planning: accidental repair resubmission fails.
    result = await app.advance(request())
    if sys.argv[2] == "started":
        assert result.blocker_or_replan_reason == "behavior_repair_interrupted"
    else:
        assert result.kind == FeatureTransitionKind.BEHAVIOR_REPAIR_APPLIED
        result = await app.advance(request())
        assert result.scenario_id == "feature--repair-1--REQ-006"

asyncio.run(main())
"""
    child = subprocess.run([sys.executable, "-c", program, str(tmp_path), phase],
                           capture_output=True, text=True, timeout=30)
    assert child.returncode == 0, child.stdout + child.stderr
    assert len(gateway.requests) == 1
