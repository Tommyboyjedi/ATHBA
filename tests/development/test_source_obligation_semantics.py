"""Source domain authority must not invent invalid-input behavior."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.development.behavior_contract_domain import BehaviorContract
from core.development.source_obligation_semantics import ObligationType, classify_obligation, validate_contract_authority
from core.development.specification_domain import SourceRequirementClause, SpecificationChecklistItem
from core.development.behavior_contract_coordinator import BehaviorContractPlanner, ContractPlanningRequest
from core.execution.reasoning_gateway import ReasoningResult

FROZEN = json.loads((Path(__file__).parent / "fixtures/campaign_shopping_basket.json").read_text())["contract"]


def test_retained_shopping_basket_invented_error_is_rejected():
    with pytest.raises(ValueError, match="source does not specify rejection"):
        validate_contract_authority(BehaviorContract.from_dict(FROZEN))


def test_domain_alone_does_not_require_a_red_or_invalid_input_behavior():
    clause = SourceRequirementClause("D", "Inputs are non-negative integers.", "validation")
    assert clause.obligation_type == ObligationType.PRECONDITION.value
    assert classify_obligation(clause.text, clause.kind) == ObligationType.PRECONDITION
    payload = json.loads(json.dumps(FROZEN))
    payload["error_semantics"] = []
    item = payload["observable_requirements"][1]
    item["error_expectation"] = None
    item["test_hint"] = "Add one valid item and observe the count."
    contract = BehaviorContract.from_dict(payload)
    assert contract.observable_requirements[1].error_expectation is None


def test_explicit_rejection_has_its_own_behavioral_authority():
    source = "Reject negative values with DomainError."
    clause = SourceRequirementClause("E", source, "validation", source_quote=source, subject=source)
    assert clause.obligation_type == ObligationType.ERROR_BEHAVIOR.value
    assert clause.source_context(source) == source
    assert SourceRequirementClause.from_dict(clause.to_dict()) == clause


def test_named_error_must_be_explicit_even_when_rejection_is_required():
    payload = json.loads(json.dumps(FROZEN))
    payload["requirement_source"] += " Reject negative prices."
    payload["error_semantics"] = ["Reject negative prices."]
    payload["observable_requirements"][1]["error_expectation"] = "Raise ValueError for negative prices."
    with pytest.raises(ValueError, match="error identifier"):
        validate_contract_authority(BehaviorContract.from_dict(payload))


@pytest.mark.parametrize("source,kind,expected", [
    ("Calling current() returns the stored value.", "behavior", "observable_behavior"),
    ("Reading current() does not change the accumulated state.", "invariant", "invariant"),
    ("The value is a supported identifier.", "validation", "precondition"),
    ("Invalid values return false.", "validation", "error_behavior"),
    ("Use no external dependencies.", "constraint", "mechanical_assurance"),
    ("Keep all state in memory.", "constraint", "non_persistence_assurance"),
    ("The parameter must be named amount.", "constraint", "naming"),
])
def test_small_language_neutral_classification(source, kind, expected):
    assert classify_obligation(source, kind).value == expected


def test_persisted_classification_cannot_change():
    item = SpecificationChecklistItem("C", "Keep it in memory.", "constraint",
        source_quote="Keep it in memory.", subject="in memory")
    data = item.to_dict()
    assert data["obligation_type"] == "non_persistence_assurance"
    data["obligation_type"] = "observable_behavior"
    with pytest.raises(ValueError, match="obligation classification"):
        SpecificationChecklistItem.from_dict(data)


def test_provenance_cannot_authorize_invented_error_clause():
    clause = SourceRequirementClause("E", "Invalid values raise ValueError.", "validation",
        source_quote="Values are non-negative integers.", subject="non-negative integers")
    with pytest.raises(ValueError, match="source does not specify rejection"):
        clause.source_context("Values are non-negative integers.")


@pytest.mark.asyncio
async def test_contract_invented_rejection_uses_existing_one_correction():
    payload = json.loads(json.dumps(FROZEN))
    corrected = json.loads(json.dumps(payload))
    corrected["error_semantics"] = []
    corrected["observable_requirements"][1].update(
        error_expectation=None, test_hint="Add a valid item and observe the count.")
    class Clauses:
        async def create_clauses(self, **kwargs):
            return [SourceRequirementClause.from_dict(x) for x in payload["source_clauses"]]
    class Gateway:
        def __init__(self):
            self.requests = []
        async def reason(self, request):
            self.requests.append(request)
            return ReasoningResult(json.dumps(payload if len(self.requests) == 1 else corrected))
    gateway = Gateway()
    result = await BehaviorContractPlanner(gateway, Clauses()).create_contract(
        ContractPlanningRequest("basket", payload["requirement_source"],
            payload["production_paths"], payload["test_paths"]))
    assert result.observable_requirements[1].error_expectation is None
    assert len(gateway.requests) == 2
    feedback = json.loads(gateway.requests[1].prompt)
    assert "source does not specify rejection" in feedback["validation_error"]
    assert feedback["invalid_contract_draft"] == json.dumps(payload)


@pytest.mark.asyncio
async def test_fresh_source_clauses_require_real_provenance():
    from core.development.behavior_contract_coordinator import RequirementClausePlanner, SourceClausePlanningFailure
    class Gateway:
        async def reason(self, request):
            return ReasoningResult(json.dumps({"clauses": [
                {"ref": "D", "text": "Values are integers.", "kind": "validation"}]}))
    with pytest.raises(SourceClausePlanningFailure) as caught:
        await RequirementClausePlanner(Gateway()).create_clauses(
            project_id="domain", requirement_text="Values are integers.")
    assert len(caught.value.attempts) == 2
    assert all("grounded source_quote" in x.validation_error for x in caught.value.attempts)


@pytest.mark.asyncio
async def test_structural_split_error_receives_one_correction_and_retains_both():
    from tests.development.test_mechanical_checklist_split import Gateway, request, response
    from core.development.specification_atomization import SpecificationChecklistPlanner
    invalid = response()
    invalid["children"][1] = dict(invalid["children"][0])
    gateway = Gateway([invalid, response()])
    result = await SpecificationChecklistPlanner(gateway).split_item(request())
    assert result.disposition == "split"
    assert len(result.attempts) == len(gateway.requests) == 2
    feedback = json.loads(gateway.requests[1].prompt)
    assert "partition every parent conjunct" in feedback["validation_error"]
    assert result.attempts[0].response == json.dumps(invalid)


@pytest.mark.asyncio
async def test_invalid_split_exhaustion_is_not_unsplittable():
    from tests.development.test_mechanical_checklist_split import Gateway, request, response
    from core.development.specification_atomization import SpecificationChecklistPlanner
    invalid = response()
    invalid["children"][1] = dict(invalid["children"][0])
    result = await SpecificationChecklistPlanner(Gateway([invalid, invalid])).split_item(request())
    assert result.disposition == "exhausted"
    assert result.rejection_reason == "invalid_split_response_exhausted"
    assert len(result.attempts) == 2


def test_explicit_error_operator_in_source_is_retained_with_a_narrow_subject():
    item = SpecificationChecklistItem("E", "Reject unsupported values.", "validation",
        source_quote="Reject unsupported values.", subject="unsupported values")
    assert item.obligation_type == ObligationType.ERROR_BEHAVIOR.value
    assert item.source_context("Reject unsupported values.") == "Reject unsupported values."


def test_precondition_without_behavior_cannot_be_misclassified_as_a_test_frontier():
    from core.development.behavior_contract_domain import BehaviorContractRequirement
    source = "Values are non-negative integers."
    clause = SourceRequirementClause("D", source, "validation")
    behavior = BehaviorContractRequirement("B", ["D"], "Valid values", "Value belongs to domain", "Check domain")
    with pytest.raises(ValueError, match="at least one test-evidence"):
        validate_contract_authority(BehaviorContract("domain", "project", "Component", "capability", source, [clause],
            [behavior], [], ["component.txt"], ["tests/example.txt"]))


def test_split_attempts_and_classification_survive_restart():
    from core.development.reconciliation_progress import ChecklistSplitProgress
    from core.development.specification_domain import ChecklistAtomizationAttempt
    item = SpecificationChecklistItem("C", "Keep it in memory.", "constraint",
        source_quote="Keep it in memory.", subject="in memory")
    progress = ChecklistSplitProgress("exhausted", "No valid correction.", attempts=(
        ChecklistAtomizationAttempt("first raw", "child_identical_to_parent"),
        ChecklistAtomizationAttempt("second raw", "duplicate_children")))
    restored = ChecklistSplitProgress.from_dict(progress.to_dict())
    assert restored == progress
    assert SpecificationChecklistItem.from_dict(item.to_dict()) == item


@pytest.mark.asyncio
async def test_four_failures_planner_correction_rejects_invented_error_then_narrows(tmp_path):
    from tests.development.test_behavior_replanning import pending_application, split_payload
    from core.development.strict_tdd_feature_replan import advance_replan, FeatureReplanContext
    from core.development.behavior_replan_domain import BehaviorReplanPhase
    app, gateway, _, _, _, transition = await pending_application(tmp_path)
    state = app.states.load("feature")
    parent = state.behavior_replans[-1].request.parent
    invalid = split_payload(parent.to_dict())
    invalid["children"][0]["error_expectation"] = "Raise ValueError."
    gateway.payload = [invalid, split_payload(parent.to_dict())]
    # Use the same production application transitions, preserving the four recorded failures.
    from tests.development.test_strict_tdd_feature_application import request
    for _ in range(4):
        transition = await app.advance(request())
    state = app.states.load("feature")
    record = state.behavior_replans[-1]
    assert record.phase == BehaviorReplanPhase.SUPERSEDED
    assert len(record.request.tester_failures.attempts) == 4
    assert record.correction_attempted
    assert len(record.rejected_responses) == 1
    assert "source does not specify rejection" in record.validation_errors[0]
    assert len(gateway.requests) == 2

def test_historical_malformed_requirement_can_be_loaded_for_bounded_repair():
    contract = BehaviorContract.from_dict(FROZEN)
    assert contract.observable_requirements[1].error_expectation
    with pytest.raises(ValueError, match="source does not specify rejection"):
        validate_contract_authority(contract)

def test_positive_persistence_is_behavior_and_negative_persistence_is_assurance():
    assert classify_obligation("Persist records across sessions.", "constraint") == ObligationType.BEHAVIOR
    item = SpecificationChecklistItem("P", "State must not persist.", "constraint", modality="forbidden",
        source_quote="State must not persist.", subject="persist")
    assert item.obligation_type == ObligationType.NON_PERSISTENCE.value
