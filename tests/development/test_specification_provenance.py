"""Prove source citations without trusting Deducer prose or adding model calls."""
import json
from pathlib import Path

import pytest

from core.development.specification_atomization import (
    ChecklistAtomizationFailure, ChecklistAtomizationRequest, SpecificationChecklistPlanner,
)
from core.development.specification_provenance import resolve_source_quote
from core.execution.reasoning_gateway import ReasoningResult


COMPOUND = "Keep the implementation dependency-free and in memory."
CONJOINED = (
    "there are a series of conjoined processes that demonstrate significant "
    "arbitration services to the ingestor."
)
SHOPPING_BASKET = "Adding bread for 3 and milk for 2 must produce an item count of 2 and a total price of 5."
TEMPERATURE_TRACKER = "Recording 10, 20 and 30 must produce latest() == 30 and average() == 20."
FIXTURE = Path(__file__).parent / "fixtures" / "pr30_atomization_omission.json"


class RecordedGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(text=self.responses.pop(0))


def item(quote, subject="in memory", modality="required", text="Keep the implementation in memory."):
    return {"ref": "REQ-1", "text": text, "kind": "constraint",
            "modality": modality, "source_quote": quote, "subject": subject}


def response(payload):
    return json.dumps({"items": [payload]})


@pytest.mark.parametrize("quote", [
    COMPOUND,
    "dependency-free",
    "in memory.",
    "Keep the implementation ... in memory.",
    "Keep the implementation … in memory.",
    "Keep ... dependency-free ... in memory.",
    "Keep\t...\tdependency-free  ...  in memory.",
    "Keep...dependency-free...in memory.",
    "Keep the implementation dependency-free in memory",
])
def test_verbatim_exact_or_ordered_source_citations_pass(quote):
    provenance = resolve_source_quote(COMPOUND, quote)
    assert provenance.grounds_subject("in memory" if "memory" in quote else "dependency-free")
    assert "dependency-free and in memory" in provenance.context
    assert provenance.source_runs
    assert provenance.match_spans


@pytest.mark.parametrize("source,quote,subject,expected_run", [
    (CONJOINED, "conjoined processes demonstrate arbitration to the ingestor", "arbitration", "arbitration"),
    (CONJOINED, "conjoined processes ... demonstrate ... arbitration ... to the ingestor", "arbitration", "arbitration"),
    (SHOPPING_BASKET, "Adding bread for 3 and milk for 2 must produce ... a total price of 5", "total price of 5", "a total price of 5"),
    (TEMPERATURE_TRACKER, "Recording 10, 20 and 30 must produce ... average() == 20", "average() == 20", "average() == 20"),
    (COMPOUND, "Keep the implementation ... in memory", "in memory", "in memory"),
])
def test_reported_ordered_citations_retain_original_source_runs(source, quote, subject, expected_run):
    provenance = resolve_source_quote(source, quote)
    assert provenance.context == source
    assert expected_run in provenance.source_runs
    assert provenance.grounds_subject(subject)


@pytest.mark.parametrize("quote", [
    "in memory ... Keep the implementation",
    "Keep the implementation ... on disk.",
    "The implementation should store everything in RAM.",
    "Keep ... stored in RAM.",
    "... in memory.",
    "Keep the implementation ...",
    "Keep ... ... in memory.",
    "Keep ...... in memory.",
    "Keep .... in memory.",
    "Keep .. in memory.",
    "Keep ... .",
    "...",
    "",
    " ",
    "keep ... in memory.",
    "Keep the imple ... in memory.",
    "Keep ... memory ... in memory.",
])
def test_unprovable_or_malformed_citations_fail_closed(quote):
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(COMPOUND, quote)


@pytest.mark.parametrize("separator", [
    ". ", "! ", "? ", "; ", ": ", "\n", "\r\n", "\u2028", "\u2029",
    " — ", " – ",
])
def test_ordered_citations_cannot_stitch_across_source_passages(separator):
    source = "Keep the implementation dependency-free" + separator + "The cache is in memory."
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(source, "Keep the implementation ... in memory.")


def test_matching_does_not_reuse_or_overlap_an_earlier_token():
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote("alpha beta.", "alpha beta ... beta.")
    provenance = resolve_source_quote("alpha beta alpha.", "alpha ... alpha.")
    assert provenance.quoted_segments == ("alpha", "alpha.")
    assert provenance.source_runs == ("alpha", "alpha.")


def test_source_search_can_find_one_later_complete_passage_without_stitching():
    source = "Keep the implementation on disk. " + COMPOUND
    provenance = resolve_source_quote(source, "Keep ... in memory.")
    assert provenance.context.strip() == COMPOUND


@pytest.mark.parametrize("subject,expected", [
    ("in memory", True), ("IN MEMORY", True), ("implementation", True),
    ("dependency-free", False), ("implementation in memory", False), ("...", False),
])
def test_omission_subject_must_belong_to_one_retained_source_run(subject, expected):
    provenance = resolve_source_quote(COMPOUND, "Keep the implementation ... in memory.")
    assert provenance.grounds_subject(subject) is expected


def test_exact_quote_path_keeps_literal_punctuation_and_original_subject_rule():
    source = "First clause; second clause. Literal ... marker."
    provenance = resolve_source_quote(source, "First clause; second clause.")
    assert provenance.quoted_segments == ("First clause; second clause.",)
    assert provenance.context == "First clause; second clause."
    assert provenance.grounds_subject("SECOND CLAUSE")
    assert resolve_source_quote(source, "Literal ... marker.").quoted_segments == ("Literal ... marker.",)


def test_token_matching_preserves_identifiers_numbers_and_operators():
    source = "Calling record_temperature(-5) must preserve value != expected."
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(source, "Calling record -5")
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(source, "value == expected")
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(source, "Calling record_temperature 5")
    provenance = resolve_source_quote(source, "record_temperature ( -5 )")
    assert provenance.source_runs == ("record_temperature(-5)",)


def test_ambiguous_abbreviated_source_attribution_fails_closed():
    source = COMPOUND + " " + COMPOUND
    with pytest.raises(ValueError, match="ambiguous"):
        resolve_source_quote(source, "Keep ... in memory")


@pytest.mark.asyncio
@pytest.mark.parametrize("attempt_index", [0, 1])
async def test_exact_live_pr30_omission_failure_now_accepts_both_obligations_without_repair(attempt_index):
    fixture = json.loads(FIXTURE.read_text())
    requirement = Path("docs/evidence/pr30-20260910/live-requirement.txt").read_text()
    assert requirement == fixture["requirement_text"]
    raw = fixture["attempts"][attempt_index]["response"]
    gateway = RecordedGateway([raw])
    result = await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", requirement))
    assert len(result.checklist.items) == 7
    dependency, memory = result.checklist.items[-2:]
    assert (dependency.subject, dependency.source_quote) == (
        "dependency-free", "Keep the implementation dependency-free")
    assert (memory.subject, memory.source_quote) == (
        "in memory", "Keep the implementation ... in memory.")
    assert len(gateway.requests) == len(result.attempts) == 1
    assert result.attempts[0].response == raw
    assert result.attempts[0].validation_error is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source,quote,subject,text", [
    (SHOPPING_BASKET, "Adding bread for 3 and milk for 2 must produce ... a total price of 5", "total price of 5", "Adding the two priced items totals five."),
    (TEMPERATURE_TRACKER, "Recording 10, 20 and 30 must produce ... average() == 20", "average() == 20", "The average after three readings is twenty."),
    (COMPOUND, "Keep the implementation ... in memory", "in memory", "State is retained only in memory."),
])
async def test_reported_citations_pass_real_checklist_decoding_without_repair(source, quote, subject, text):
    raw = response(item(quote, subject, text=text))
    gateway = RecordedGateway([raw])
    result = await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", source))
    assert result.checklist.items[0].source_quote == quote
    assert result.checklist.items[0].text == text
    assert len(gateway.requests) == len(result.attempts) == 1
    assert result.attempts[0].validation_error is None


@pytest.mark.asyncio
async def test_complete_source_passage_can_support_separate_rephrased_obligations_and_reload():
    full_quote = SHOPPING_BASKET
    raw = json.dumps({"items": [
        item(full_quote, "item count of 2", text="The example leaves two basket entries."),
        {**item(full_quote, "total price of 5", text="The example totals five currency units."), "ref": "REQ-2"},
    ]})
    gateway = RecordedGateway([raw])
    result = await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", SHOPPING_BASKET))
    restored = type(result.checklist).from_dict(result.checklist.to_dict())
    assert [entry.subject for entry in restored.items] == ["item count of 2", "total price of 5"]
    assert [entry.source_quote for entry in restored.items] == [full_quote, full_quote]
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source,quote,subject,modality", [
    ("Caching and persistence are optional.", "Caching ... are optional.", "Caching", "non_goal"),
    ("Clients must not persist records in memory.", "Clients must not ... in memory.", "in memory", "forbidden"),
    ("Clients must not persist records in memory.", "Clients ... in memory.", "in memory", "forbidden"),
    ("Caching and persistence are not required.", "Caching ... not required.", "Caching", "non_goal"),
    (COMPOUND, "Keep ... in memory.", "in memory", "required"),
])
async def test_omission_modality_uses_original_source_context(source, quote, subject, modality):
    gateway = RecordedGateway([response(item(quote, subject, modality))])
    result = await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", source))
    assert result.checklist.items[0].modality == modality
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("source,quote,subject,modality,error", [
    ("Clients must not persist records in memory.", "Clients ... in memory.", "in memory", "required", "contradicts"),
    ("The service must not store results.", "The service must store results", "store results", "required", "contradicts"),
    ("Caching and persistence are not required.", "Caching ... persistence", "Caching", "required", "contradicts"),
    (COMPOUND, "Keep ... in memory.", "in memory", "non_goal", "non-goal requires"),
    (COMPOUND, "Keep ... in memory.", "dependency-free", "required", "field subject"),
    (COMPOUND, "Keep ... in memory.", "Keep in memory", "required", "field subject"),
])
async def test_invalid_modality_or_subject_retains_two_attempt_failure_policy(source, quote, subject, modality, error):
    raw = response(item(quote, subject, modality))
    gateway = RecordedGateway([raw, raw, response(item(COMPOUND))])
    with pytest.raises(ChecklistAtomizationFailure) as raised:
        await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", source))
    assert len(gateway.requests) == len(raised.value.attempts) == 2
    assert len(gateway.responses) == 1
    assert all(error in attempt.validation_error for attempt in raised.value.attempts)
    assert all("REQ-1" in attempt.validation_error for attempt in raised.value.attempts)


@pytest.mark.asyncio
async def test_invalid_omission_receives_item_specific_repair_feedback_and_same_policy():
    invalid = response(item("in memory ... Keep the implementation"))
    repaired = response(item("Keep ... in memory."))
    gateway = RecordedGateway([invalid, repaired])
    result = await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", COMPOUND))
    assert [request.purpose for request in gateway.requests] == [
        "athba_specification_checklist", "athba_specification_checklist_repair"]
    assert len(result.attempts) == 2
    assert result.attempts[0].response == invalid
    assert "field source_quote" in result.attempts[0].validation_error
    assert "REQ-1" in result.attempts[0].validation_error
    assert result.attempts[1].response == repaired
    assert result.attempts[1].validation_error is None
    prompts = [json.loads(request.prompt) for request in gateway.requests]
    assert prompts[0]["rules"] == prompts[1]["rules"]
    assert "Specification Deducer" in prompts[1]["instruction"]


def split_request():
    from core.development.specification_atomization import ChecklistSplitRequest

    return ChecklistSplitRequest(
        project_id="p", requirement_text=COMPOUND, parent_ref="REQ", parent_text=COMPOUND,
        parent_kind="constraint", parent_modality="required", parent_source_quote=COMPOUND,
        parent_subject="implementation", individual_no_results=(), final_revision="a" * 40,
    )


def split_payload(memory_quote: str) -> str:
    children = [item("Keep the implementation dependency-free", "dependency-free"),
                item(memory_quote)]
    children[0]["text"] = "Remain dependency-free."
    return json.dumps({
        "disposition": "split", "rationale": "Two independent constraints.", "children": children,
    })


@pytest.mark.asyncio
async def test_valid_split_path_uses_ordered_source_provenance_rule():
    gateway = RecordedGateway([split_payload("Keep ... in memory.")])

    result = await SpecificationChecklistPlanner(gateway).split_item(split_request())

    assert result.disposition == "split"
    assert len(gateway.requests) == 1
    assert result.rejection_reason is None
    assert [child.ref for child in result.children] == ["REQ-S001", "REQ-S002"]
    assert [child.subject for child in result.children] == ["dependency-free", "in memory"]
    assert len(result.attempts) == 1


@pytest.mark.asyncio
async def test_invalid_split_response_is_repaired_with_precise_feedback():
    invalid = split_payload("in memory ... Keep the implementation")
    repaired = split_payload("Keep ... in memory.")
    gateway = RecordedGateway([invalid, repaired])

    result = await SpecificationChecklistPlanner(gateway).split_item(split_request())

    assert result.disposition == "split"
    assert [request.purpose for request in gateway.requests] == [
        "athba_specification_checklist_split",
        "athba_specification_checklist_split_repair",
    ]
    assert len(result.attempts) == 2
    assert result.attempts[0].response == invalid
    assert "field source_quote" in result.attempts[0].validation_error
    assert result.attempts[1].response == repaired
    assert result.attempts[1].validation_error is None
    prompts = [json.loads(request.prompt) for request in gateway.requests]
    assert prompts[0]["rules"] == prompts[1]["rules"]
    assert prompts[1]["validation_error"] == result.attempts[0].validation_error


@pytest.mark.asyncio
async def test_repeated_invalid_split_response_is_distinct_from_genuine_unsplittable():
    invalid = split_payload("in memory ... Keep the implementation")
    gateway = RecordedGateway([invalid, invalid])

    result = await SpecificationChecklistPlanner(gateway).split_item(split_request())

    assert result.disposition == "unsplittable"
    assert result.rejection_reason == "invalid_split_response_exhausted"
    assert "bounded schema repair" in result.rationale
    assert len(result.attempts) == 2
    assert all(attempt.validation_error for attempt in result.attempts)


@pytest.mark.asyncio
async def test_genuine_unsplittable_split_response_remains_terminal_without_repair():
    gateway = RecordedGateway([json.dumps({
        "disposition": "unsplittable",
        "rationale": "The parent is already a single grounded obligation.",
    })])

    result = await SpecificationChecklistPlanner(gateway).split_item(split_request())

    assert result.disposition == "unsplittable"
    assert result.rejection_reason is None
    assert len(gateway.requests) == 1
    assert len(result.attempts) == 1


def test_shared_adjectives_remain_in_one_source_passage():
    source = "Keep the implementation simple and deterministic and testable."
    provenance = resolve_source_quote(source, "Keep ... deterministic ... testable.")
    assert provenance.context == source
