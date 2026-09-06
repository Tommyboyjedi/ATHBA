"""Deterministic Planner contract and feature recovery regression tests."""
import json
from dataclasses import replace

import pytest

from core.development.behavior_contract_coordinator import BehaviorContractPlanner
from core.development.behavior_contract_domain import BehaviorContractRequirement
from core.development.behavior_replan_domain import (
    BehaviorReplanBlocker, BehaviorReplanDisposition, BehaviorReplanPhase, BehaviorReplanPolicy,
)
from core.development.behavior_replan_validation import BehaviorSplitValidationContext, replan_worthy
from core.development.scenario_drafting_domain import ScenarioDraftAttempt, ScenarioDraftRunState
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.strict_tdd_feature_replan import require_replan
from core.development.strict_tdd_transitions import FeatureTransitionKind
from core.execution.reasoning_gateway import ReasoningResult
from tests.development.test_strict_tdd_feature_application import contract, request, service


class ReplanGateway:
    def __init__(self, payload=None):
        self.requests = []
        self.payload = payload

    async def reason(self, request):
        assert request.purpose == "athba_behavior_requirement_replan"
        self.requests.append(request)
        parent = json.loads(request.prompt)["request"]["parent"]
        payload = self.payload if self.payload is not None else split_payload(parent)
        if isinstance(payload, Exception):
            raise payload
        return ReasoningResult(json.dumps(payload) if not isinstance(payload, str) else payload)


def split_payload(parent):
    return {
        "disposition": "split", "rationale": "Separate two observable dimensions for independent tests.",
        "coverage_rationale": "Both source obligations are retained without additions.",
        "children": [dict(
            source_refs=[parent["source_refs"][index % len(parent["source_refs"])]],
            summary=f"Narrow dimension {index}", observable_outcome=f"Observable unit {parent['ref'].replace('-', '')} part {index}",
            test_hint=f"Observe dimension {index}", error_expectation=parent["error_expectation"],
            preserves_state_on_failure=parent["preserves_state_on_failure"],
            narrowing_rationale=f"Only source dimension {index}; the other is handled by its sibling.",
        ) for index in range(2)],
    }


def exhausted(behavior, revision="trusted", scenario_id=None, statuses=None):
    statuses = statuses or ["insufficient_evidence", "timed_out_no_candidate", "insufficient_evidence", "insufficient_evidence"]
    attempts = tuple(ScenarioDraftAttempt(
        index, f"work-{behavior.ref}-{index}", None,
        None if status == "timed_out_no_candidate" else f"candidate-{index}", f"evidence/{index}",
        status, "Candidate does not independently prove the required outcome",
        no_candidate_outcome=status if status == "timed_out_no_candidate" else None,
    ) for index, status in enumerate(statuses, 1))
    return ScenarioDraftRunState(
        scenario_id or f"feature--{behavior.ref}", behavior.ref, tuple(behavior.source_refs), "python", "pytest",
        "tests/test_widget.py", revision, attempts, status="attempts_exhausted",
    )


async def pending_application(tmp_path, payload=None, count=1):
    planned = contract("feature", count)
    app, _, gatekeeper, scenarios, reconciler = service(tmp_path, planned)
    gateway = ReplanGateway(payload)
    # Persist planning normally before installing the real Planner adapter with fake reasoning.
    for _ in range(3):
        await app.advance(request())
    app.contract_planner = BehaviorContractPlanner(gateway)
    original = scenarios.execute

    async def execute(value):
        result = await original(value)
        if value.behavior.ref == planned.observable_requirements[-1].ref:
            draft = exhausted(value.behavior, value.canonical_development_base, f"feature--{value.behavior.ref}")
            return replace(result, scenario_id=draft.scenario_id, status="attempts_exhausted", draft_state=draft,
                           canonical_development_base=value.canonical_development_base)
        return result

    scenarios.execute = execute
    while True:
        transition = await app.advance(request())
        if transition.kind == FeatureTransitionKind.BEHAVIOR_REPLAN_REQUIRED:
            break
        assert transition.kind != FeatureTransitionKind.BLOCKED
    return app, gateway, gatekeeper, scenarios, reconciler, transition


@pytest.mark.asyncio
async def test_split_replaces_parent_in_order_preserves_completed_and_resumes(tmp_path):
    app, gateway, gatekeeper, scenarios, reconciler, required = await pending_application(tmp_path, count=5)
    before = app.states.load("feature")
    assert before.status == "running" and len(before.completed_behaviors) == 4
    assert required.fingerprint.pending_action == "behavior_replan_required"
    assert gateway.requests == []
    received = await app.advance(request())
    assert received.kind == FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED
    saved = app.states.load("feature")
    assert saved.behavior_replans[-1].phase == BehaviorReplanPhase.RECEIVED
    assert saved.canonical_development_base == before.canonical_development_base
    sent = json.loads(gateway.requests[0].prompt)["request"]
    assert len(sent["tester_failures"]["attempts"]) == 4
    assert len(sent["completed_requirements"]) == 4
    assert "must not be changed" in sent["preservation_instruction"]
    assert sent["canonical_revision"] == before.canonical_development_base
    # Reconstruct the service with a deserialized repository and the same deterministic ports.
    from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService, StrictTddFeatureDependencies
    from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
    app = StrictTddFeatureApplicationService(StrictTddFeatureDependencies(
        app.environment, StrictTddFeatureRepository(tmp_path / "features"), app.contract_planner,
        gatekeeper, scenarios, reconciler,
    ))
    split = await app.advance(request())
    assert split.kind == FeatureTransitionKind.BEHAVIOR_SPLIT
    after = app.states.load("feature")
    assert after.completed_behaviors == before.completed_behaviors
    assert after.canonical_development_base == before.canonical_development_base
    assert after.gatekeeper_payload == before.gatekeeper_payload
    assert after.behavior_replans[-1].phase == BehaviorReplanPhase.SUPERSEDED
    assert after.behavior_replans[-1].child_refs == ("B-4-S001", "B-4-S002")
    result = await app.run(request())
    assert result.current_status == "completed"
    assert [item.behavior_ref for item in result.completed_behaviors] == ["B-0", "B-1", "B-2", "B-3", "B-4-S001", "B-4-S002"]
    assert len(gateway.requests) == len(gatekeeper.requests) == 1
    assert [item.behavior.ref for item in scenarios.requests] == ["B-0", "B-1", "B-2", "B-3", "B-4", "B-4-S001", "B-4-S002"]
    assert reconciler.calls[0].gatekeeper_payload == before.gatekeeper_payload
    assert StrictTddFeatureState.from_dict(after.to_dict()) == after


@pytest.mark.asyncio
async def test_unsplittable_durably_blocks_without_more_tester_work(tmp_path):
    payload = {"disposition": "unsplittable", "rationale": "Atomic obligation cannot be divided without changing its meaning.", "coverage_rationale": "", "children": []}
    app, gateway, _, scenarios, _, _ = await pending_application(tmp_path, payload)
    count = len(scenarios.requests)
    result = await app.run(request())
    assert result.blocked_reason == "behavior_unsplittable"
    record = app.states.load("feature").behavior_replans[-1]
    assert record.phase == BehaviorReplanPhase.UNSPLITTABLE
    assert record.response.rationale == payload["rationale"]
    assert len(record.request.tester_failures.attempts) == 4
    assert record.request.source_clauses and record.request.canonical_revision
    assert await app.run(request()) == result
    assert len(gateway.requests) == 1 and len(scenarios.requests) == count


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["same_parent", "duplicate", "source", "coverage", "id", "dependency", "empty", "prose", "provider"])
async def test_nonprogress_protocol_and_provider_fail_closed_once(tmp_path, invalid):
    parent = contract("feature").observable_requirements[0].to_dict()
    payload = split_payload(parent)
    if invalid == "same_parent":
        payload["children"][0]["observable_outcome"] = parent["observable_outcome"]
    elif invalid == "duplicate":
        payload["children"][1] = dict(payload["children"][0])
    elif invalid == "source":
        payload["children"][0]["source_refs"] = ["invented"]
    elif invalid == "coverage":
        payload["coverage_rationale"] = ""
    elif invalid == "id":
        payload["children"][0]["ref"] = "arbitrary"
    elif invalid == "dependency":
        payload["children"][0]["depends_on"] = ["arbitrary"]
    elif invalid == "empty":
        payload["children"] = []
    elif invalid == "prose":
        payload = "not JSON"
    else:
        payload = RuntimeError("unavailable")
    app, gateway, _, scenarios, reconciler, _ = await pending_application(tmp_path, payload)
    count = len(scenarios.requests)
    result = await app.run(request())
    assert result.current_status == "blocked"
    assert len(gateway.requests) == 1 and len(scenarios.requests) == count
    assert reconciler.calls == []
    assert app.states.load("feature").behavior_replans[-1].detail


@pytest.mark.asyncio
async def test_started_without_response_blocks_on_resume_without_second_replan(tmp_path):
    app, gateway, _, scenarios, _, _ = await pending_application(tmp_path)
    state = app.states.load("feature")
    app.states.save(replace(state, behavior_replans=(replace(state.behavior_replans[0], phase=BehaviorReplanPhase.STARTED),)))
    result = await app.run(request())
    assert result.blocked_reason == BehaviorReplanBlocker.INTERRUPTED.value
    assert gateway.requests == []
    assert len(scenarios.requests) == 1


@pytest.mark.parametrize("statuses", [
    ["timed_out_no_candidate"] * 4,
    ["intent_review_protocol_failure"] * 4,
    ["scenario_harness_failure"] * 4,
    ["insufficient_evidence", "intent_review_protocol_failure", "insufficient_evidence", "insufficient_evidence"],
])
def test_infrastructure_exhaustion_is_not_decomposition(statuses):
    assert not replan_worthy(exhausted(contract("feature").observable_requirements[0], statuses=statuses))


@pytest.mark.asyncio
async def test_recursive_child_split_preserves_lineage(tmp_path):
    app, gateway, _, scenarios, _, _ = await pending_application(tmp_path)
    original = scenarios.execute
    async def execute(value):
        result = await original(value)
        if value.behavior.ref == "B-0-S002":
            draft = exhausted(value.behavior, value.canonical_development_base, "feature--B-0-S002")
            return replace(result, scenario_id=draft.scenario_id, status="attempts_exhausted", draft_state=draft,
                           canonical_development_base=value.canonical_development_base)
        return result
    scenarios.execute = execute
    result = await app.run(request())
    assert result.current_status == "completed"
    records = app.states.load("feature").behavior_replans
    assert len(records) == len(gateway.requests) == 2
    assert records[1].request.lineage == ("B-0",)
    assert records[1].split_depth == 1
    assert records[1].child_refs == ("B-0-S002-S001", "B-0-S002-S002")
    assert [item.behavior_ref for item in result.completed_behaviors] == ["B-0-S001", "B-0-S002-S001", "B-0-S002-S002"]


def test_observed_signalboard_shape_requests_replan_not_feature_blocker():
    from core.development.specification_domain import SourceRequirementClause
    from core.development.strict_tdd_feature_domain import CompletedBehaviorReference
    planned = contract("feature", 5)
    parent = BehaviorContractRequirement("REQ-005", ["PR16-007", "PR16-008"], "Architectural constraints",
                                         "Component is in-memory and dependency-free", "Verify no external dependencies or persistence side-effects")
    previous = [replace(item, ref=f"REQ-{index:03d}") for index, item in enumerate(planned.observable_requirements[:4], 1)]
    planned = replace(planned, observable_requirements=[*previous, parent], source_clauses=[
        *planned.source_clauses[:4], SourceRequirementClause("PR16-007", "State is in memory", "behavior"),
        SourceRequirementClause("PR16-008", "No external runtime dependencies", "behavior"),
    ])
    state = StrictTddFeatureState("feature", "hash", "running", planned.to_dict(), current_scenario_id="feature--REQ-005",
        completed_behaviors=tuple(CompletedBehaviorReference(item.ref, f"feature--{item.ref}", "trusted", ("senior-approved",)) for item in previous),
        canonical_ref="refs/heads/main", canonical_development_base="trusted")
    result = require_replan(state, exhausted(parent))
    assert result.status == "running" and result.blocked_reason is None
    assert result.behavior_replans[0].phase == BehaviorReplanPhase.REQUIRED
    assert len(result.behavior_replans[0].request.completed_requirements) == 4


@pytest.mark.asyncio
async def test_total_split_guard_escalates_without_another_planner_submission(tmp_path):
    app, gateway, _, scenarios, _, _ = await pending_application(tmp_path)
    app.replan_policy = BehaviorReplanPolicy(max_splits=1)
    original = scenarios.execute
    async def execute(value):
        result = await original(value)
        if value.behavior.ref == "B-0-S001":
            draft = exhausted(value.behavior, value.canonical_development_base, "feature--B-0-S001")
            return replace(result, scenario_id=draft.scenario_id, status="attempts_exhausted", draft_state=draft,
                           canonical_development_base=value.canonical_development_base)
        return result
    scenarios.execute = execute
    result = await app.run(request())
    assert result.blocked_reason == "behavior_unsplittable"
    assert len(gateway.requests) == 1
    assert "safety budget" in app.states.load("feature").behavior_replans[-1].detail


@pytest.mark.asyncio
async def test_replan_lifecycle_projects_required_received_split_and_unsplittable(tmp_path):
    from core.development.strict_tdd_transition_provenance import StrictTddTransitionEventProjector, StrictTddTransitionProjectionRequest, StrictTddTerminalPolicy, StrictTddTerminalPolicyRequest
    from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleRunContext
    app, _, _, _, _, required = await pending_application(tmp_path)
    received = await app.advance(request())
    split = await app.advance(request())
    context = StrictTddLifecycleRunContext("run", "feature", "Widget", "test-head", "fake-only")
    for transition, event in zip((required, received, split), ("behavior_replan_required", "behavior_split_received", "behavior_split")):
        projected = StrictTddTransitionEventProjector().project(StrictTddTransitionProjectionRequest(context, transition, 1))
        assert projected[0].event_kind.value == event
        assert StrictTddTerminalPolicy().decide(StrictTddTerminalPolicyRequest(transition, None, frozenset())).disposition.value == "continue"
    blocked = replace(split, kind=FeatureTransitionKind.BLOCKED, blocker_or_replan_reason="behavior_unsplittable",
                      transition_path=replace(split.transition_path, feature_kind=FeatureTransitionKind.BLOCKED))
    projected = StrictTddTransitionEventProjector().project(StrictTddTransitionProjectionRequest(context, blocked, 2))
    assert projected[0].event_kind.value == "behavior_unsplittable"


def test_split_validation_rejects_reordered_duplicates_prior_structure_and_missing_coverage():
    from core.development.behavior_replan_domain import BehaviorReplanRecord
    from core.development.behavior_replanning import _parse
    from core.development.behavior_replan_validation import validate_split, structure_digest
    planned = contract("feature")
    state = StrictTddFeatureState("feature", "hash", "running", planned.to_dict(), current_scenario_id="feature--B-0",
                                 canonical_ref="refs/heads/main", canonical_development_base="trusted")
    record = require_replan(state, exhausted(planned.observable_requirements[0])).behavior_replans[0]
    payload = split_payload(record.request.parent.to_dict())
    response = _parse(json.dumps(payload), record.request)
    received = replace(record, response=response, phase=BehaviorReplanPhase.RECEIVED)
    digest = validate_split(received, BehaviorSplitValidationContext(planned, (), BehaviorReplanPolicy()))
    assert digest == structure_digest(response.children)
    prior = replace(record, structure_digest=digest)
    with pytest.raises(ValueError, match="repeated identical split"):
        validate_split(received, BehaviorSplitValidationContext(planned, (prior,), BehaviorReplanPolicy()))
    payload["children"][1]["observable_outcome"] = " ".join(reversed(payload["children"][0]["observable_outcome"].split()))
    duplicate = replace(received, response=_parse(json.dumps(payload), record.request))
    with pytest.raises(ValueError, match="duplicate children"):
        validate_split(duplicate, BehaviorSplitValidationContext(planned, (), BehaviorReplanPolicy()))
    from core.development.specification_domain import SourceRequirementClause
    parent = replace(record.request.parent, source_refs=["SRC-0", "SRC-extra"])
    planned = replace(planned, observable_requirements=[parent], source_clauses=[*planned.source_clauses, SourceRequirementClause("SRC-extra", "extra obligation", "behavior")])
    changed = replace(record.request, parent=parent, source_clauses=tuple(planned.source_clauses))
    incomplete = replace(received, request=changed)
    with pytest.raises(ValueError, match="drops parent source coverage"):
        validate_split(incomplete, BehaviorSplitValidationContext(planned, (), BehaviorReplanPolicy()))


def test_split_rewires_pending_dependencies_without_changing_completed_requirements():
    from core.development.behavior_replan_domain import BehaviorReplanRecord
    from core.development.behavior_replanning import _parse
    from core.development.strict_tdd_feature_replan import _replace_parent
    planned = contract("feature", 3)
    parent = planned.observable_requirements[1]
    following = replace(planned.observable_requirements[2], depends_on=[parent.ref])
    planned = replace(planned, observable_requirements=[planned.observable_requirements[0], parent, following])
    state = StrictTddFeatureState("feature", "hash", "running", planned.to_dict(), current_scenario_id="feature--B-1",
                                 canonical_ref="refs/heads/main", canonical_development_base="trusted")
    record = require_replan(state, exhausted(parent)).behavior_replans[0]
    record = replace(record, response=_parse(json.dumps(split_payload(parent.to_dict())), record.request))
    updated = _replace_parent(planned, record)
    assert updated.observable_requirements[0] == planned.observable_requirements[0]
    assert updated.observable_requirements[-1].depends_on == ["B-1-S001", "B-1-S002"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["timed_out_no_candidate", "intent_review_protocol_failure"])
async def test_feature_infrastructure_exhaustion_blocks_without_planner(tmp_path, status):
    app, _, _, scenarios, reconciler = service(tmp_path, contract("feature"))
    for _ in range(3):
        await app.advance(request())
    gateway = ReplanGateway()
    app.contract_planner = BehaviorContractPlanner(gateway)
    original = scenarios.execute
    async def execute(value):
        result = await original(value)
        draft = exhausted(value.behavior, value.canonical_development_base, "feature--B-0", [status] * 4)
        return replace(result, scenario_id=draft.scenario_id, status="attempts_exhausted", draft_state=draft,
                       canonical_development_base=value.canonical_development_base)
    scenarios.execute = execute
    result = await app.run(request())
    assert result.current_status == "blocked"
    assert result.blocked_reason == "attempts_exhausted"
    assert gateway.requests == [] and reconciler.calls == []
    assert not app.states.load("feature").behavior_replans
