"""Bounded consolidation protocol; raw submissions are visible to the journal owner."""
from dataclasses import replace
import json

import pytest

from core.development.consolidation_reasoning import (
    AUTHOR_PURPOSE, FORMAT_PURPOSE, MAX_CONSOLIDATION_CONTEXT_BYTES, MAX_CONSOLIDATION_PROMPT_BYTES, PROPOSAL_PURPOSE,
    REVIEW_PURPOSE, ConsolidationContextLimit, ConsolidationCorrection, ConsolidationReasoning,
    ConsolidationReasoningContext,
)
from core.execution.reasoning_gateway import ReasoningResult

REFS = ("REQ-A", "REQ-B", "fragment:old-a:setup", "fragment:old-a:assert", "fragment:old-b:assert")
NAME = "tests/evidence.ext::combined"


def context():
    return ConsolidationReasoningContext("checkpoint-1", "project-1", json.dumps({
        "language": "example-language", "framework": "example-runner",
        "selected_obligations": [{"ref": "REQ-A"}, {"ref": "REQ-B"}],
        "selected_tests": [{"name": "old-a", "source": "setup A; observe A"},
                           {"name": "old-b", "source": "setup B; observe B"}],
        "interface_facts": {"public_operation": "observe"},
    }), REFS, NAME)


class Gateway:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    async def reason(self, request):
        self.calls.append(request)
        return ReasoningResult(next(self.responses))


@pytest.mark.asyncio
async def test_raw_submission_and_format_correction_are_explicit_and_bounded_by_caller():
    invalid = "nested malformed original response"
    valid = json.dumps({"decision": "NO", "description": "independent examples cannot safely combine"})
    gateway = Gateway((invalid, valid))
    reasoning = ConsolidationReasoning(gateway)
    selected = context()
    request = reasoning.proposal_request(selected)

    raw = await reasoning.invoke(request)
    assert raw.text == invalid
    assert request.purpose == PROPOSAL_PURPOSE
    assert len(gateway.calls) == 1
    with pytest.raises(ValueError):
        reasoning.decode_proposal(selected, raw.text)
    assert len(gateway.calls) == 1, "decoding cannot hide a model submission"

    correction = reasoning.correction_request(request, ConsolidationCorrection(raw.text, "exact decoder error"))
    repair_payload = json.loads(correction.prompt)
    assert correction.purpose == FORMAT_PURPOSE
    assert repair_payload["invalid_response"] == invalid
    assert repair_payload["validation_error"] == "exact decoder error"
    assert repair_payload["required_output"] == json.loads(request.prompt)["required_output"]
    assert correction.project_id == selected.project_id
    assert reasoning.decode_proposal(selected, (await reasoning.invoke(correction)).text) is None
    assert len(gateway.calls) == 2
    assert json.loads(request.prompt)["selected_completed_evidence"]["selected_tests"][1]["source"] == "setup B; observe B"


def test_strict_flat_protocol_preserves_every_authority_and_reuses_intent_verdict():
    reasoning = ConsolidationReasoning(Gateway(()))
    selected = context()
    proposal = reasoning.decode_proposal(selected, json.dumps({"decision": "YES", "description": "retain both independent cases"}))
    assert proposal is not None
    assert reasoning.author_request(selected, proposal).purpose == AUTHOR_PURPOSE
    with pytest.raises(ValueError):
        reasoning.decode_proposal(selected, json.dumps({"wrapper": {"decision": "YES", "description": "nested"}}))
    with pytest.raises(ValueError):
        reasoning.decode_proposal(selected, '{"decision":"NO","decision":"YES","description":"duplicate"}')

    payload = {"source": "complete ordinary test retaining independent setup A and setup B", "coverage": [
        {"authority_ref": ref, "replacement_test": NAME, "description": "preserved exact observation " + ref}
        for ref in REFS]}
    replacement = reasoning.decode_replacement(selected, json.dumps(payload))
    assert tuple(link.authority_ref for link in replacement.coverage) == REFS
    assert len(reasoning.review_request(selected, replacement).prompt) > len(replacement.source)
    assert reasoning.review_request(selected, replacement).purpose == REVIEW_PURPOSE

    variants = [
        {**payload, "coverage": payload["coverage"][:-1]},
        {**payload, "coverage": [*payload["coverage"], payload["coverage"][0]]},
        {**payload, "coverage": [{**entry, "replacement_test": "another-test"} for entry in payload["coverage"]]},
        {**payload, "wrapper": "unrequested"},
    ]
    for invalid in variants:
        with pytest.raises(ValueError):
            reasoning.decode_replacement(selected, json.dumps(invalid))
    fence = chr(96) * 3
    with pytest.raises(ValueError):
        reasoning.decode_replacement(selected, fence + "json\n" + json.dumps(payload) + "\n" + fence)
    with pytest.raises(ConsolidationContextLimit):
        replace(selected, semantic_context_json=json.dumps({"oversized": "x" * MAX_CONSOLIDATION_CONTEXT_BYTES}))

    approved = {"disposition": "approved", "feedback": "every original observation is independently preserved",
                "evidence_refs": list(REFS)}
    result = reasoning.decode_review(selected, json.dumps(approved))
    assert result.status == "approved"
    assert result.scenario_id == selected.checkpoint_id
    for evidence in [list(REFS[:-1]), [*REFS, "invented-reference"]]:
        with pytest.raises(ValueError):
            reasoning.decode_review(selected, json.dumps({**approved, "evidence_refs": evidence}))

    huge_replacement = replace(replacement, source="x" * MAX_CONSOLIDATION_PROMPT_BYTES)
    with pytest.raises(ConsolidationContextLimit, match="serialized"):
        reasoning.review_request(selected, huge_replacement)
    with pytest.raises(ConsolidationContextLimit, match="serialized"):
        reasoning.correction_request(reasoning.proposal_request(selected),
            ConsolidationCorrection("x" * MAX_CONSOLIDATION_PROMPT_BYTES, "format error"))



@pytest.mark.asyncio
async def test_format_correction_cannot_become_a_second_semantic_submission(tmp_path):
    from core.development.consolidation_journal import ConsolidationJournal
    from core.development.consolidation_reasoning import ConsolidationProposal
    from core.development.consolidation_submission import ConsolidationProtocolFailure, ConsolidationSubmission

    selected = context()
    source = "ordinary test retaining both independent observations"
    payload = {"source": source, "coverage": [
        {"authority_ref": ref, "replacement_test": NAME, "description": "preserved " + ref}
        for ref in REFS]}
    fence = chr(96) * 3
    fenced = fence + "json\n" + json.dumps(payload) + "\n" + fence
    invalid_coverage = json.dumps({**payload, "coverage": {"wrong": "shape"}})
    proposal = {"decision": "NO", "description": "preservation cannot be established"}
    review = {"disposition": "repair_required", "feedback": "independent setup was lost", "evidence_refs": []}
    cases = [
        ("fenced", fenced, json.dumps(payload), AUTHOR_PURPOSE, True, 2),
        ("coverage", invalid_coverage, json.dumps(payload), AUTHOR_PURPOSE, True, 2),
        ("changed-source", invalid_coverage, json.dumps({**payload, "source": "different semantics"}), AUTHOR_PURPOSE, False, 2),
        ("decision", json.dumps({**proposal, "extra": True}), json.dumps({**proposal, "decision": "YES"}), PROPOSAL_PURPOSE, False, 2),
        ("feedback", json.dumps({**review, "extra": True}), json.dumps({**review, "feedback": "all observations preserved"}), REVIEW_PURPOSE, False, 2),
        ("unrecoverable", "not JSON and no recoverable source", json.dumps(payload), AUTHOR_PURPOSE, False, 1),
    ]
    for name, original, corrected, purpose, accepted, calls in cases:
        gateway = Gateway((original, corrected))
        reasoning = ConsolidationReasoning(gateway)
        journal = ConsolidationJournal(tmp_path, name)
        submission = ConsolidationSubmission(reasoning, journal)
        if purpose == AUTHOR_PURPOSE:
            request = reasoning.author_request(selected, ConsolidationProposal("retain both"))
            decoder = lambda text: reasoning.decode_replacement(selected, text)
        elif purpose == PROPOSAL_PURPOSE:
            request = reasoning.proposal_request(selected)
            decoder = lambda text: reasoning.decode_proposal(selected, text)
        else:
            replacement = reasoning.decode_replacement(selected, json.dumps(payload))
            request = reasoning.review_request(selected, replacement)
            decoder = lambda text: reasoning.decode_review(selected, text)
        if accepted:
            result = await submission.decode(("phase", request), decoder)
            assert result.source == source
        else:
            with pytest.raises(ConsolidationProtocolFailure):
                await submission.decode(("phase", request), decoder)
        assert len(gateway.calls) == calls
        original_record = json.loads((journal.root / "phase.json").read_text())
        assert original_record["result"]["text"] == original
        if calls == 2:
            repair_record = json.loads((journal.root / "phase-format-correction.json").read_text())
            assert repair_record["result"]["text"] == corrected


@pytest.mark.asyncio
async def test_readiness_wait_resumes_before_admission_but_transport_wait_cannot_replay(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from core.development.consolidation_journal import ConsolidationJournal
    from core.development.consolidation_submission import ConsolidationSubmission
    from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
    from core.execution.rack_ai_runtime import RackAiResourceWait
    from core.llm.contracts.provider import NormalizedResult

    ready = Mock(side_effect=RackAiResourceWait("service is preparing"))
    dispatch = Mock(return_value=NormalizedResult(text="accepted response", usage={}, raw={}))

    def invoke(request):
        ready("test-service")  # The provider also checks readiness before transport.
        return dispatch(request)

    provider = SimpleNamespace(
        runtime_access=SimpleNamespace(reservation=SimpleNamespace(ready=ready), service="test-service"),
        invoke=invoke,
    )
    gateway = ProviderReasoningGateway(provider, "test-model")
    reasoning = ConsolidationReasoning(gateway)
    journal = ConsolidationJournal(tmp_path, "readiness-checkpoint")
    request = reasoning.proposal_request(context())
    submission = ConsolidationSubmission(reasoning, journal)
    with pytest.raises(RackAiResourceWait, match="preparing"):
        await submission.submit(request, "proposal")
    assert dispatch.call_count == 0
    assert not (journal.root / "proposal.json").exists()
    assert reasoning.invocation_count == 0

    ready.side_effect = None
    resumed = ConsolidationSubmission(
        ConsolidationReasoning(gateway), ConsolidationJournal(tmp_path, "readiness-checkpoint"))
    assert await resumed.submit(request, "proposal") == "accepted response"
    assert dispatch.call_count == 1
    assert json.loads((journal.root / "proposal.json").read_text())["status"] == "completed"

    ready.side_effect = RackAiResourceWait("service no longer ready")
    calls_before_cache = ready.call_count
    assert await resumed.submit(request, "proposal") == "accepted response"
    assert ready.call_count == calls_before_cache and dispatch.call_count == 1

    ready.side_effect = None
    dispatch.side_effect = RackAiResourceWait("scoped model transport: ReadTimeout")
    with pytest.raises(RackAiResourceWait, match="transport"):
        await resumed.submit(request, "review")
    pending_path = journal.root / "review.json"
    pending = pending_path.read_bytes()
    assert json.loads(pending)["status"] == "pending"
    assert dispatch.call_count == 2

    ready.side_effect = RackAiResourceWait("service no longer ready")
    calls_before_resume = ready.call_count
    another_resume = ConsolidationSubmission(
        ConsolidationReasoning(gateway), ConsolidationJournal(tmp_path, "readiness-checkpoint"))
    with pytest.raises(ValueError, match="uncertain; submission will not replay"):
        await another_resume.submit(request, "review")
    assert pending_path.read_bytes() == pending
    assert ready.call_count == calls_before_resume and dispatch.call_count == 2
