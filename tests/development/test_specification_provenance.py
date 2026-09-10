"""Prove exact source spans without trusting atomizer prose or adding model calls."""
import json
from pathlib import Path

import pytest

from core.development.specification_atomization import (
    ChecklistAtomizationFailure, ChecklistAtomizationRequest, SpecificationChecklistPlanner,
)
from core.development.specification_provenance import resolve_source_quote
from core.execution.reasoning_gateway import ReasoningResult


COMPOUND = "Keep the implementation dependency-free and in memory."
FIXTURE = Path(__file__).parent / "fixtures" / "pr30_atomization_omission.json"


class RecordedGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(text=self.responses.pop(0))


def item(quote, subject="in memory", modality="required"):
    return {"ref": "REQ-1", "text": "Keep the implementation in memory.", "kind": "constraint",
            "modality": modality, "source_quote": quote, "subject": subject}


def response(payload):
    return json.dumps({"items": [payload]})


@pytest.mark.parametrize("quote", [
    COMPOUND,
    "dependency-free",
    "in memory.",
    "Keep the implementation ... in memory.",
    "Keep ... dependency-free ... in memory.",
    "Keep\t...\tdependency-free  ...  in memory.",
    "Keep...dependency-free...in memory.",
])
def test_verbatim_exact_or_ordered_omission_quotes_pass(quote):
    provenance = resolve_source_quote(COMPOUND, quote)
    assert provenance.grounds_subject("in memory" if "memory" in quote else "dependency-free")
    assert "dependency-free and in memory" in provenance.context


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
    "Keep … in memory.",
    "Keep ... .",
    "...",
    "",
    " ",
    "keep ... in memory.",
    "Keep the imple ... in memory.",
    "Keep ... memory ... in memory.",
])
def test_unprovable_or_malformed_omissions_fail_closed(quote):
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(COMPOUND, quote)


@pytest.mark.parametrize("separator", [
    ". ", "! ", "? ", "; ", ": ", ", ", "\n", "\r\n", "\u2028", "\u2029",
    " — ", " – ", " but ", " whereas ", " although ", " while ", " however ",
    " unless ", " otherwise ",
])
def test_omissions_cannot_stitch_across_sentence_or_clause_boundaries(separator):
    source = "Keep the implementation dependency-free" + separator + "The cache is in memory."
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(source, "Keep the implementation ... in memory.")


def test_matching_does_not_reuse_or_overlap_an_earlier_segment():
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote("alpha beta.", "alpha beta ... beta.")
    provenance = resolve_source_quote("alpha beta alpha.", "alpha ... alpha.")
    assert provenance.quoted_segments == ("alpha", "alpha.")


def test_source_search_can_find_one_later_complete_clause_without_stitching():
    source = "Keep the implementation on disk. " + COMPOUND
    provenance = resolve_source_quote(source, "Keep ... in memory.")
    assert provenance.context.strip() == COMPOUND


@pytest.mark.parametrize("subject,expected", [
    ("in memory", True), ("IN MEMORY", True), ("implementation", True),
    ("dependency-free", False), ("implementation in memory", False), ("...", False),
])
def test_omission_subject_must_belong_to_one_retained_segment(subject, expected):
    provenance = resolve_source_quote(COMPOUND, "Keep the implementation ... in memory.")
    assert provenance.grounds_subject(subject) is expected


def test_exact_quote_path_keeps_literal_punctuation_and_original_subject_rule():
    source = "First clause; second clause. Literal ... marker."
    provenance = resolve_source_quote(source, "First clause; second clause.")
    assert provenance.quoted_segments == ("First clause; second clause.",)
    assert provenance.context == "First clause; second clause."
    assert provenance.grounds_subject("SECOND CLAUSE")
    assert resolve_source_quote(source, "Literal ... marker.").quoted_segments == ("Literal ... marker.",)


def test_whitespace_inside_segments_is_not_rewritten():
    with pytest.raises(ValueError, match="provenance"):
        resolve_source_quote(COMPOUND, "Keep  the implementation ... in memory.")


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
    ("Caching and persistence are not required.", "Caching ... persistence", "Caching", "required", "contradicts"),
    (COMPOUND, "Keep ... in memory.", "in memory", "non_goal", "non-goal requires"),
    (COMPOUND, "Keep ... in memory.", "dependency-free", "required", "provenance"),
    (COMPOUND, "Keep ... in memory.", "Keep in memory", "required", "provenance"),
])
async def test_invalid_modality_or_subject_retains_two_attempt_failure_policy(source, quote, subject, modality, error):
    raw = response(item(quote, subject, modality))
    gateway = RecordedGateway([raw, raw, response(item(COMPOUND))])
    with pytest.raises(ChecklistAtomizationFailure) as raised:
        await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", source))
    assert len(gateway.requests) == len(raised.value.attempts) == 2
    assert len(gateway.responses) == 1
    assert all(error in attempt.validation_error for attempt in raised.value.attempts)


@pytest.mark.asyncio
async def test_invalid_omission_receives_only_existing_repair_and_same_provenance_validation():
    invalid = response(item("in memory ... Keep the implementation"))
    repaired = response(item("Keep ... in memory."))
    gateway = RecordedGateway([invalid, repaired])
    result = await SpecificationChecklistPlanner(gateway).atomize(ChecklistAtomizationRequest("p", COMPOUND))
    assert [request.purpose for request in gateway.requests] == [
        "athba_specification_checklist", "athba_specification_checklist_repair"]
    assert len(result.attempts) == 2
    assert result.attempts[0].response == invalid
    assert "provenance" in result.attempts[0].validation_error
    assert result.attempts[1].response == repaired
    assert result.attempts[1].validation_error is None
    prompts = [json.loads(request.prompt) for request in gateway.requests]
    assert prompts[0]["rules"] == prompts[1]["rules"]


@pytest.mark.asyncio
@pytest.mark.parametrize("memory_quote,disposition", [
    ("Keep ... in memory.", "split"),
    ("in memory ... Keep the implementation", "unsplittable"),
])
async def test_existing_split_path_uses_the_same_bounded_provenance_rule(memory_quote, disposition):
    from core.development.specification_atomization import ChecklistSplitRequest
    children = [item("Keep the implementation dependency-free", "dependency-free"),
                item(memory_quote)]
    children[0]["text"] = "Remain dependency-free."
    gateway = RecordedGateway([json.dumps({
        "disposition": "split", "rationale": "Two independent constraints.", "children": children,
    })])
    result = await SpecificationChecklistPlanner(gateway).split_item(ChecklistSplitRequest(
        project_id="p", requirement_text=COMPOUND, parent_ref="REQ", parent_text=COMPOUND,
        parent_kind="constraint", parent_modality="required", parent_source_quote=COMPOUND,
        parent_subject="implementation", individual_no_results=(), final_revision="a" * 40,
    ))
    assert result.disposition == disposition
    assert len(gateway.requests) == 1
    if disposition == "split":
        assert [child.ref for child in result.children] == ["REQ-S001", "REQ-S002"]
        assert [child.subject for child in result.children] == ["dependency-free", "in memory"]
    else:
        assert result.rejection_reason == "invalid_split_response"
