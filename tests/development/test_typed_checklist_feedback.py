"""All typed checklist errors must be available to the one bounded correction."""
import json
from pathlib import Path

import pytest

from core.development.specification_atomization import (
    ChecklistAtomizationFailure, ChecklistAtomizationRequest, SpecificationChecklistPlanner,
)
from core.execution.reasoning_gateway import ReasoningResult

FIXTURE = json.loads((Path(__file__).parent / "fixtures/shoppingbasket_checklist_draft.json").read_text())


class Gateway:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(json.dumps(self.responses[len(self.requests) - 1]))


def corrected():
    draft = json.loads(json.dumps(FIXTURE["draft"]))
    draft["items"][3]["kind"] = "validation"
    draft["items"][7]["obligation_type"] = "non_persistence_assurance"
    return draft


@pytest.mark.asyncio
async def test_one_bounded_correction_receives_all_retained_type_errors():
    gateway = Gateway([FIXTURE["draft"], corrected()])
    result = await SpecificationChecklistPlanner(gateway).atomize(
        ChecklistAtomizationRequest("typed-repair", FIXTURE["requirement_text"]))
    assert len(gateway.requests) == len(result.attempts) == 2
    feedback = json.loads(gateway.requests[1].prompt)
    error = feedback["validation_error"]
    assert "REQ-004" in error and "kind=validation" in error
    assert "precondition" in error
    assert "REQ-008" in error and "non_persistence_assurance" in error
    assert "mechanical_assurance" in error
    assert result.attempts[0].response == json.dumps(FIXTURE["draft"])
    assert result.checklist.items[3].obligation_type == "precondition"
    assert result.checklist.items[7].obligation_type == "non_persistence_assurance"


@pytest.mark.asyncio
async def test_unchanged_invalid_correction_exhausts_without_normalization():
    gateway = Gateway([FIXTURE["draft"], FIXTURE["draft"]])
    with pytest.raises(ChecklistAtomizationFailure) as caught:
        await SpecificationChecklistPlanner(gateway).atomize(
            ChecklistAtomizationRequest("typed-exhaustion", FIXTURE["requirement_text"]))
    assert len(gateway.requests) == len(caught.value.attempts) == 2
    assert all("REQ-004" in a.validation_error and "REQ-008" in a.validation_error
               for a in caught.value.attempts)
    assert all(a.response == json.dumps(FIXTURE["draft"]) for a in caught.value.attempts)


@pytest.mark.asyncio
async def test_initial_schema_explains_kind_and_classification_relationship():
    gateway = Gateway([corrected()])
    result = await SpecificationChecklistPlanner(gateway).atomize(
        ChecklistAtomizationRequest("typed-first", FIXTURE["requirement_text"]))
    prompt = json.loads(gateway.requests[0].prompt)
    rules = " ".join(prompt["rules"])
    assert "kind=validation" in rules and "precondition" in rules
    assert "non_persistence_assurance" in rules
    assert len(result.attempts) == 1
