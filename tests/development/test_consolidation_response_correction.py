"""Local response correction proofs; no live models or qualification."""
import json
from pathlib import Path

import pytest

from core.development.consolidation_journal import ConsolidationJournal
from core.development.consolidation_reasoning import (
    ConsolidationProposal, ConsolidationReasoning, ConsolidationReasoningContext,
)
from core.development.consolidation_submission import ConsolidationProtocolFailure, ConsolidationSubmission
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from tests.development.consolidation_helpers import ControlledReasoning, git, make_fixture
from tests.development.test_consolidation_reasoning import Gateway, NAME, REFS, context

FENCE = chr(96) * 3


def replacement(selected, source="ordinary source with literal " + FENCE + " and \\n"):
    return {"source": source, "coverage": [
        {"authority_ref": ref, "replacement_test": selected.replacement_test_name,
         "description": "Preserved independent observation " + ref}
        for ref in selected.authority_refs]}


def selected_from_request(request):
    body = json.loads(request.prompt)
    return ConsolidationReasoningContext(body["checkpoint_id"], request.project_id,
        json.dumps(body["selected_completed_evidence"]), tuple(body["authority_refs"]),
        body["replacement_test_name"])


@pytest.mark.asyncio
async def test_bare_and_single_outer_fences_validate_without_correction(tmp_path):
    selected = context()
    payload = replacement(selected)
    for label in ("bare", "plain", "json"):
        gateway = Gateway(())
        reasoning = ConsolidationReasoning(gateway)
        proposal = {"decision": "YES", "description": "Preserve both cases"}
        review = {"disposition": "approved", "feedback": "Both cases survive", "evidence_refs": list(REFS)}
        decoder_pairs = [
            (reasoning.proposal_request(selected), proposal, lambda text: reasoning.decode_proposal(selected, text)),
            (reasoning.author_request(selected, ConsolidationProposal("both")), payload,
             lambda text: reasoning.decode_replacement(selected, text)),
            (reasoning.review_request(selected, reasoning.decode_replacement(selected, json.dumps(payload))),
             review, lambda text: reasoning.decode_review(selected, text)),
        ]
        for number, (request, body, decode) in enumerate(decoder_pairs):
            raw = json.dumps(body)
            if label != "bare":
                raw = " \n" + FENCE + ("json" if label == "json" else "") + "\n" + raw + "\n" + FENCE + " \n"
            gateway.responses = iter((raw,))
            journal = ConsolidationJournal(tmp_path, label + str(number))
            result = await ConsolidationSubmission(reasoning, journal).decode(("phase", request), decode)
            assert result == decode(json.dumps(body))
            assert not (journal.root / "phase-format-correction.json").exists()
            assert json.loads((journal.root / "phase.json").read_text())["result"]["text"] == raw
            trace = json.loads((journal.root / "phase-validation.json").read_text())
            assert trace["initial"]["wrapper_normalized"] == (label != "bare")
            assert trace["disposition"] == "accepted"
        assert len(gateway.calls) == 3


def test_ambiguous_wrapping_duplicate_keys_and_schema_remain_rejected():
    reasoning = ConsolidationReasoning(Gateway(()))
    selected = context()
    valid = '{"decision":"YES","description":"both"}'
    invalid = [
        "Explanation\n" + FENCE + "json\n" + valid + "\n" + FENCE,
        FENCE + "json\n" + valid + "\n" + FENCE + "\ntrailing prose",
        FENCE + "json\n" + valid,
        FENCE + "json\n" + valid + "\n" + FENCE + "\n" + FENCE + "json\n" + valid + "\n" + FENCE,
        FENCE + "json\n" + '{"decision":"NO","decision":"YES","description":"duplicate"}' + "\n" + FENCE,
        FENCE + "json\n" + '{"wrapper":' + valid + "}" + "\n" + FENCE,
        FENCE + "python\n" + valid + "\n" + FENCE,
        valid + valid,
        '{"decision":"MAYBE","description":"unsupported"}',
    ]
    for raw in invalid:
        with pytest.raises(ValueError):
            reasoning.decode_proposal(selected, raw)


@pytest.mark.asyncio
async def test_retained_two_of_eleven_gets_informed_source_preserving_correction(tmp_path):
    retained = json.loads((Path(__file__).parents[1] / "fixtures/consolidation_coverage_omission.json").read_text())
    request = ReasoningRequest(**retained["request"])
    selected = selected_from_request(request)
    original = json.loads(retained["response"])
    complete = replacement(selected, original["source"])
    complete["coverage"][:2] = original["coverage"]
    corrected = FENCE + "json\n" + json.dumps(complete, indent=2) + "\n" + FENCE
    gateway = Gateway((retained["response"], corrected))
    reasoning = ConsolidationReasoning(gateway)
    journal = ConsolidationJournal(tmp_path, "retained")
    result = await ConsolidationSubmission(reasoning, journal).decode(("replacement", request),
        lambda text: reasoning.decode_replacement(selected, text))
    prompt = json.loads(gateway.calls[1].prompt)
    assert prompt["source"] == original["source"] == result.source
    assert prompt["existing_coverage"] == original["coverage"]
    assert prompt["replacement_test_name"] == selected.replacement_test_name
    assert prompt["authority_refs"] == list(selected.authority_refs)
    assert prompt["missing_authority_refs"] == list(selected.authority_refs[2:])
    assert len(prompt["missing_authority_refs"]) == 9
    assert prompt["selected_completed_evidence"] == json.loads(request.prompt)["selected_completed_evidence"]
    assert len(result.coverage) == 11 and len(gateway.calls) == 2
    trace = json.loads((journal.root / "replacement-validation.json").read_text())
    assert trace["initial"]["missing_authority_refs"] == prompt["missing_authority_refs"]
    assert trace["correction"]["wrapper_normalized"] and trace["disposition"] == "accepted"


@pytest.mark.asyncio
async def test_coverage_changes_and_invalid_corrections_exhaust_one_shared_slot(tmp_path):
    selected = context()
    complete = replacement(selected)
    incomplete = {**complete, "coverage": complete["coverage"][:2]}
    altered_entry = [dict(entry) for entry in complete["coverage"]]
    altered_entry[0]["description"] = "Changed original mapping"
    altered_target = [dict(entry) for entry in complete["coverage"]]
    altered_target[0]["replacement_test"] = "other::test"
    variants = [
        {**complete, "source": complete["source"] + "changed"},
        {**complete, "coverage": altered_entry},
        {**complete, "coverage": altered_target},
        incomplete,
        {**complete, "coverage": [*complete["coverage"], complete["coverage"][0]]},
        {**complete, "coverage": [*complete["coverage"], {
            "authority_ref": "invented", "replacement_test": NAME, "description": "invented"}]},
        "malformed corrective response",
    ]
    for index, revised in enumerate(variants):
        raw = json.dumps(incomplete)
        corrected = revised if isinstance(revised, str) else json.dumps(revised)
        gateway = Gateway((raw, corrected))
        reasoning = ConsolidationReasoning(gateway)
        request = reasoning.author_request(selected, ConsolidationProposal("both"))
        journal = ConsolidationJournal(tmp_path, str(index))
        submission = ConsolidationSubmission(reasoning, journal)
        for _ in range(2):  # Resume must reuse the same two durable responses.
            with pytest.raises(ConsolidationProtocolFailure, match="initial validation:.*correction validation:"):
                await submission.decode(("replacement", request), lambda text: reasoning.decode_replacement(selected, text))
        assert len(gateway.calls) == 2
        trace = json.loads((journal.root / "replacement-validation.json").read_text())
        assert trace["initial"]["error"] == "coverage must map every selected authority exactly once"
        assert trace["correction"]["error"] and trace["disposition"] == "rejected"
        assert json.loads((journal.root / "replacement.json").read_text())["result"]["text"] == raw
        assert json.loads((journal.root / "replacement-format-correction.json").read_text())["result"]["text"] == corrected

    # A format correction that reveals missing coverage cannot earn a third call.
    malformed = {**complete, "extra": True}
    gateway = Gateway((json.dumps(malformed), json.dumps(incomplete)))
    reasoning = ConsolidationReasoning(gateway)
    request = reasoning.author_request(selected, ConsolidationProposal("both"))
    journal = ConsolidationJournal(tmp_path, "format-then-coverage")
    with pytest.raises(ConsolidationProtocolFailure):
        await ConsolidationSubmission(reasoning, journal).decode(("replacement", request),
            lambda text: reasoning.decode_replacement(selected, text))
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
async def test_corrected_coverage_still_requires_independent_semantic_review(tmp_path):
    scripted = ControlledReasoning(approve=False)

    class OmittedCoverage:
        def __init__(self):
            self.requests = scripted.requests

        async def reason(self, request):
            body = json.loads(request.prompt)
            if request.purpose == "athba_completed_req_consolidation_coverage_correction":
                self.requests.append(request)
                preserved = list(body["existing_coverage"])
                additions = [{"authority_ref": ref, "replacement_test": body["replacement_test_name"],
                    "description": "Controlled claim for independent review"}
                    for ref in body["missing_authority_refs"]]
                return ReasoningResult(json.dumps({"source": body["source"], "coverage": preserved + additions}))
            result = await scripted.reason(request)
            if request.purpose == "athba_completed_req_consolidation_test":
                payload = json.loads(result.text)
                payload["coverage"] = payload["coverage"][:2]
                return ReasoningResult(json.dumps(payload))
            return result

    gateway = OmittedCoverage()
    f = make_fixture(tmp_path, gateway)
    before = git(f.root, "rev-parse", "HEAD")
    original_tests = (f.root / "tests/test_shopping_basket.py").read_bytes()
    outcome = await f.service.advance(f.context)
    assert outcome.canonical_development_base == before and outcome.evidence_consolidations == ()
    assert git(f.root, "rev-parse", "HEAD") == before
    assert (f.root / "tests/test_shopping_basket.py").read_bytes() == original_tests
    assert len(gateway.requests) == 4
    assert gateway.requests[-1].purpose == "athba_completed_req_consolidation_review"
    journals = list((f.state_root / "evidence-consolidations").glob("*/checkpoint.json"))
    diagnostic = json.loads(journals[0].read_text())["diagnostic"]
    assert diagnostic.startswith("Semantic preservation rejected:")
    assert not (journals[0].parent / "test-acceptance.json").exists()

    # A source string is not enough: the configured existing authoring adapter
    # must establish supported syntax before spending a coverage correction.
    invalid_scripted = ControlledReasoning(source="def broken():\\\\n    assert True")
    scripted = invalid_scripted
    invalid_gateway = OmittedCoverage()
    invalid = make_fixture(tmp_path / "invalid-source", invalid_gateway)
    rejected = await invalid.service.advance(invalid.context)
    assert rejected.canonical_development_base == invalid.state.canonical_development_base
    assert len(invalid_gateway.requests) == 2
    checkpoint = next((invalid.state_root / "evidence-consolidations").glob("*/checkpoint.json"))
    assert "replacement syntax/static validation:" in json.loads(checkpoint.read_text())["diagnostic"]
    assert not (checkpoint.parent / "replacement-format-correction.json").exists()


@pytest.mark.asyncio
async def test_pending_corrective_submission_never_blindly_replays(tmp_path):
    selected = context()
    payload = replacement(selected)
    raw = json.dumps({**payload, "coverage": payload["coverage"][:2]})
    calls = []

    class LostCorrection:
        async def reason(self, request):
            calls.append(request)
            if len(calls) == 1:
                return ReasoningResult(raw)
            raise ConnectionError("corrective response lost")

    reasoning = ConsolidationReasoning(LostCorrection())
    request = reasoning.author_request(selected, ConsolidationProposal("both"))
    journal = ConsolidationJournal(tmp_path, "lost-correction")
    submission = ConsolidationSubmission(reasoning, journal)
    with pytest.raises(ConnectionError, match="lost"):
        await submission.decode(("replacement", request), lambda text: reasoning.decode_replacement(selected, text))
    pending = (journal.root / "replacement-format-correction.json").read_bytes()
    assert json.loads(pending)["status"] == "pending"
    with pytest.raises(ValueError, match="uncertain; submission will not replay"):
        await submission.decode(("replacement", request), lambda text: reasoning.decode_replacement(selected, text))
    assert len(calls) == 2
    assert (journal.root / "replacement-format-correction.json").read_bytes() == pending
