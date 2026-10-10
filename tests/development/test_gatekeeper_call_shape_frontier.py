"""Known source call-shape gaps return once to the normal narrow TDD path."""
from dataclasses import replace

import pytest

from core.development.behavior_contract_domain import BehaviorContract
from core.development.feature_signature_evidence import signature_evidence
from core.development.specification_domain import SourceRequirementClause
from core.development.specification_evidence_policy import RevisionFile, SpecificationSnapshot
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from tests.development.test_strict_tdd_feature_application import contract, request, service

SOURCE = "Provide a Widget class. Calling grow(amount) changes the count."
QUOTE = "grow(amount)"
REVISION = "a" * 40
BAD = "class Widget:\n    def grow(self, value=1): pass\n"
GOOD = "class Widget:\n    def grow(self, value): pass\n"


def planned_contract():
    original = contract("feature")
    clause = SourceRequirementClause("SRC-0", "Calling grow(amount) changes the count.",
        "behavior", source_quote="Calling grow(amount) changes the count", subject=QUOTE)
    return replace(original, requirement_source=SOURCE, source_clauses=[clause])


def shape_evidence(code=BAD):
    return signature_evidence(SOURCE,
        SpecificationSnapshot(REVISION, (RevisionFile("widget.py", code),)), "python")


def test_known_violation_has_structured_source_identity():
    record = shape_evidence()
    assert record["answer"] == "NO"
    assert record["failed_signatures"] == record["required_signatures"]
    assert record["unsupported_findings"] == []
    assert record["snapshot_complete"] is True
    assert record["signature_gap_schema"] == "athba/source-call-shape-gap/v1"


@pytest.mark.asyncio
async def test_final_call_shape_gap_creates_one_frontier_and_resume_keeps_accepted_history(tmp_path):
    planned = planned_contract()
    application, planner, gatekeeper, scenarios, reconciler = service(tmp_path, planned)
    original_execute = scenarios.execute

    async def accepted(value):
        result = await original_execute(value)
        return replace(result, canonical_development_base=REVISION)

    scenarios.execute = accepted

    async def reconcile(value):
        reconciler.calls.append(value)
        code = BAD if len(value.completed_behaviors) == 1 else GOOD
        if len(reconciler.calls) == 1 and value.checkpoint:
            value.checkpoint(({"schema": "gatekeeper-progress/v1", "trusted_revision": REVISION},))
        return ({"checklist_ref": "CHK-1", "answer": "YES"}, shape_evidence(code))

    reconciler.reconcile = reconcile
    user_request = replace(request(), source_requirement=SOURCE)
    transitions = [await application.advance(user_request) for _ in range(7)]
    repair = transitions[-1]
    assert repair.kind.value == "specification_repair_planned"
    assert repair.another_transition_available
    assert not repair.rack_ai_invoked
    from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleRunContext
    from core.development.strict_tdd_transition_provenance import (
        StrictTddTransitionEventProjector, StrictTddTransitionProjectionRequest,
        StrictTddTerminalPolicy, StrictTddTerminalPolicyRequest,
    )
    context = StrictTddLifecycleRunContext("run", "feature", SOURCE, "athba", "rack")
    projected = StrictTddTransitionEventProjector().project(
        StrictTddTransitionProjectionRequest(context, repair, 7))
    assert projected[0].event_kind.value == "specification_repair_planned"
    assert projected[0].behavior_ref == repair.behavior_ref
    terminal = StrictTddTerminalPolicy().decide(StrictTddTerminalPolicyRequest(repair, None, frozenset()))
    assert terminal.disposition.value == "continue"
    saved = application.states.load("feature")
    restored = StrictTddFeatureState.from_dict(saved.to_dict())
    assert restored == saved
    assert len(saved.specification_repairs) == 1
    assert saved.specification_repairs[0].reconciliation[-1]["answer"] == "NO"
    assert saved.specification_repairs[0].reconciliation_progress == ({"schema": "gatekeeper-progress/v1", "trusted_revision": REVISION},)
    assert [item.behavior_ref for item in saved.completed_behaviors] == ["B-0"]
    updated = BehaviorContract.from_dict(saved.contract_payload)
    gap = updated.observable_requirements[-1]
    assert gap.source_refs == ["SRC-0"]
    assert gap.error_expectation is None
    assert "1 required" in gap.observable_outcome
    assert "parameter spelling" in gap.observable_outcome
    assert "ValueError" not in gap.observable_outcome
    assert saved.final_reconciliation == saved.reconciliation_progress == ()
    completed = await application.run(user_request)
    assert completed.current_status == "completed"
    assert len(completed.completed_behaviors) == 2
    assert len(planner.requests) == len(gatekeeper.requests) == 1
    assert len(reconciler.calls) == 2
    assert reconciler.calls[-1].reconciliation_progress == ()
    assert scenarios.requests[1].prior_completed_test_nodes == ("tests/test_widget.py::test_B_0",)
    assert len(application.states.load("feature").specification_repairs) == 1


def ready_state(record=None):
    from core.development.strict_tdd_feature_domain import CompletedBehaviorReference
    planned = planned_contract()
    return StrictTddFeatureState("feature", "source-hash", "running", planned.to_dict(),
        canonical_ref="refs/heads/main", canonical_development_base=REVISION,
        completed_behaviors=(CompletedBehaviorReference("B-0", "feature--B-0", REVISION, ("accepted",)),),
        final_reconciliation=({"checklist_ref": "CHK-1", "answer": "YES"}, record or shape_evidence()))


@pytest.mark.parametrize("mutation", [
    {"signature_gap_schema": "unknown"},
    {"snapshot_complete": False},
    {"unsupported_findings": ["opaque declaration"]},
    {"revision": "b" * 40},
    {"failed_signatures": []},
    {"required_signatures": []},
    {"failed_signatures": [{"owner": "Other", "name": "grow", "parameters": ["amount"], "source_quote": QUOTE}]},
    {"blocked_reason": "protocol failure"},
    {"answer": "NOT_APPLICABLE"},
    {"evidence_status": "unsupported_evidence_policy"},
])
def test_unknown_or_unbound_evidence_cannot_create_a_frontier(mutation):
    from core.development.gatekeeper_signature_frontier import plan_signature_repair
    record = shape_evidence()
    record.update(mutation)
    assert plan_signature_repair(ready_state(record)) is None


@pytest.mark.parametrize("code", [
    "@unknown\nclass Widget:\n    def grow(self, value=1): pass\n",
    "class Widget:\n    def renamed(self, value): pass\n",
    GOOD,
])
def test_unknown_lexical_or_already_correct_declaration_is_not_repaired(code):
    from core.development.gatekeeper_signature_frontier import plan_signature_repair
    assert plan_signature_repair(ready_state(shape_evidence(code))) is None


def test_repeated_same_gap_after_delivery_remains_blocking_and_preserves_archive():
    from core.development.gatekeeper_signature_frontier import plan_signature_repair
    from core.development.strict_tdd_feature_domain import CompletedBehaviorReference
    initial = ready_state()
    planned = plan_signature_repair(initial)
    ref = planned.specification_repairs[0].behavior_ref
    later = replace(planned, completed_behaviors=(*planned.completed_behaviors,
        CompletedBehaviorReference(ref, "feature--" + ref, REVISION, ("accepted-new-red",))),
        final_reconciliation=initial.final_reconciliation)
    restored = StrictTddFeatureState.from_dict(later.to_dict())
    assert plan_signature_repair(restored) is None
    assert len(restored.completed_behaviors) == 2
    assert restored.specification_repairs[0].reconciliation == initial.final_reconciliation


def test_no_fuzzy_clause_mapping_and_no_repair_of_other_blockers():
    from core.development.gatekeeper_signature_frontier import plan_signature_repair
    state = ready_state()
    contract = BehaviorContract.from_dict(state.contract_payload)
    clause = SourceRequirementClause("SRC-0", "Unrelated behavior.", "behavior")
    ungrounded = replace(contract, source_clauses=[clause])
    assert plan_signature_repair(replace(state, contract_payload=ungrounded.to_dict())) is None
    other_blocker = ({"answer": "NO", "evidence_status": "fail"}, state.final_reconciliation[-1])
    assert plan_signature_repair(replace(state, final_reconciliation=other_blocker)) is None
    assert plan_signature_repair(replace(state, completed_behaviors=())) is None


def test_current_source_only_and_no_error_or_lexical_authority():
    from core.development.gatekeeper_signature_frontier import plan_signature_repair
    planned = plan_signature_repair(ready_state())
    contract = BehaviorContract.from_dict(planned.contract_payload)
    gap = contract.observable_requirements[-1]
    assert gap.source_refs == ["SRC-0"]
    assert gap.error_expectation is None
    assert "amount" not in gap.observable_outcome
    assert "Naming" not in gap.observable_outcome
    assert "Gatekeeper" not in gap.observable_outcome
    assert "ValueError" not in gap.observable_outcome
    assert "1 required" in gap.observable_outcome


def test_public_shape_red_ignores_spelling_but_detects_defaulted_parameter():
    import inspect
    bad, good = {}, {}
    exec(BAD, bad)
    exec(GOOD, good)
    def public_shape_red(namespace):
        operation = namespace["Widget"]().grow
        parameters = tuple(inspect.signature(operation).parameters.values())
        assert len(parameters) == 1
        assert all(parameter.default is inspect.Parameter.empty for parameter in parameters)
    with pytest.raises(AssertionError):
        public_shape_red(bad)
    public_shape_red(good)


def test_required_call_shape_red_is_an_admissible_test_artifact():
    from types import SimpleNamespace
    from core.development.microcycle_domain import ScenarioSourceCandidate
    from core.development.python_pytest_adapter import PythonCandidateAssessmentFactory
    from core.development.scenario_drafting import _authoring_contract
    from core.development.semantic_api_annotations import SemanticApiAnnotation
    from tests.development.test_scenario_drafting import request as draft_request
    source = ("from widget import Widget\nimport inspect\n\ndef test_one():\n"
              "    widget=Widget()\n    widget.grow(3)\n"
              "    parameters=tuple(inspect.signature(widget.grow).parameters.values())\n"
              "    assert len(parameters)==1\n"
              "    assert all(parameter.default is inspect.Parameter.empty for parameter in parameters)\n")
    candidate = ScenarioSourceCandidate("scenario", "REQ1", "python", "tests/test_widget.py",
        source, "tests/test_widget.py::test_one", "candidate", "memory")
    result = PythonCandidateAssessmentFactory().assess(SimpleNamespace(candidate=candidate,
        production_path="widget.py", contract=_authoring_contract(draft_request("widget")),
        semantic_annotations=(SemanticApiAnnotation("grow", "invoke", QUOTE, None, "Widget", 1),),
        candidate_interface_facts=()))
    assert result.accepted, result.repair_feedback()


def test_compound_source_clause_cannot_leak_a_second_operation_to_the_frontier():
    from core.development.gatekeeper_signature_frontier import plan_signature_repair
    source = "Provide a Widget class. Calling grow(amount) changes the count and calling reset() clears it."
    original = planned_contract()
    clause = SourceRequirementClause("SRC-0", "Grow and reset behavior.", "behavior",
        source_quote="Calling grow(amount) changes the count and calling reset() clears it",
        subject="grow(amount)")
    contract = replace(original, requirement_source=source, source_clauses=[clause])
    record = signature_evidence(source,
        SpecificationSnapshot(REVISION, (RevisionFile("widget.py", BAD + "    def reset(self): pass\n"),)), "python")
    state = replace(ready_state(), contract_payload=contract.to_dict(),
        final_reconciliation=({"answer": "YES"}, record))
    assert plan_signature_repair(state) is None
