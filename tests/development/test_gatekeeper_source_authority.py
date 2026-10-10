"""Original source reaches independent proof review, never behavioral authors."""
from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_evidence_policy import SpecificationEvidenceAdapters
import json

import pytest

from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_routing import RoutedChecklistReconciler, RoutedChecklistRequest
from core.development.specification_reconciliation import AcceptedTestEvidence, ChecklistItemReconciler
from tests.development.test_test_evidence_reconciliation import FakeReasoningGateway

QUOTE = "Recording an entry adds exactly one entry"
SOURCE = ("Provide a Ledger class. " + QUOTE + ". Values are non-negative integers. "
          "Calling count() reports the number of recorded entries.")
REVISION = "a" * 40


class VerifiedCatalog:
    semantic_revision = REVISION

    def verified_source(self, evidence):
        return evidence.test_source

    def contains(self, evidence):
        return True


def source_item():
    return SpecificationChecklistItem("COUNT", "Recording an entry increases the count.",
        "behavior", source_quote=QUOTE, subject="adds exactly one entry")


def accepted(number):
    return AcceptedTestEvidence(f"tests/test_ledger.py::test_record_{number}",
        "tests/test_ledger.py", f"STEP-{number}", ["COUNT"], "b" * 40, REVISION,
        f"def test_record_{number}():\n    assert True", True)


def response(answer="NO"):
    return {"answer": answer, "selected_test_names": [], "rationale": "Selected proof is incomplete."}


@pytest.mark.asyncio
async def test_routed_proof_call_preserves_full_original_source_and_selected_authority():
    gateway = FakeReasoningGateway([response()])
    catalog = VerifiedCatalog()
    result = await RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
        RoutedChecklistRequest("project", source_item(), SOURCE, [accepted(1)], language_id="python"))
    assert result["answer"] == "NO"
    prompt = json.loads(gateway.requests[0].prompt)
    assert prompt["specification_authority"]["original_source"] == SOURCE
    assert prompt["specification_authority"]["selected_item"] == source_item().to_dict()
    assert prompt["accepted_tdd_tests"][0]["final_revision_verified"] is True
    assert len(prompt["accepted_tdd_tests"]) == 1


@pytest.mark.asyncio
async def test_original_authority_survives_each_independent_accepted_test_call():
    gateway = FakeReasoningGateway([response(), response()])
    catalog = VerifiedCatalog()
    await RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
        RoutedChecklistRequest("project", source_item(), SOURCE, [accepted(2), accepted(1)], language_id="python"))
    assert len(gateway.requests) == 2
    for request in gateway.requests:
        prompt = json.loads(request.prompt)
        assert prompt["specification_authority"]["original_source"] == SOURCE
        assert len(prompt["accepted_tdd_tests"]) == 1


@pytest.mark.asyncio
async def test_format_correction_preserves_the_decision_without_reinterpreting_source():
    from core.execution.reasoning_gateway import ReasoningResult

    class RawGateway:
        def __init__(self, responses):
            self.responses = list(responses)
            self.requests = []

        async def reason(self, request):
            self.requests.append(request)
            return ReasoningResult(text=self.responses.pop(0), provider="fake", model="fake")

    fence = chr(96) * 3
    previous = fence + "json  \n" + json.dumps(response()) + "\n" + fence
    gateway = RawGateway([previous, json.dumps(response())])
    catalog = VerifiedCatalog()
    result = await RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
        RoutedChecklistRequest("project", source_item(), SOURCE, [accepted(1)], language_id="python"))
    assert len(gateway.requests) == 2
    assert json.loads(gateway.requests[0].prompt)["specification_authority"]["original_source"] == SOURCE
    repair = json.loads(gateway.requests[1].prompt)
    assert repair["previous_response"] == previous
    assert "specification_authority" not in repair
    assert SOURCE not in gateway.requests[1].prompt
    assert result["answer"] == "NO"
    assert len(result["response_attempts"]) == 2


def test_source_authority_rejects_unresolvable_quote_and_mismatched_selector():
    from core.development.reconciliation_source_authority import ChecklistSourceAuthority
    from core.development.specification_reconciliation import ChecklistReconciliationRequest
    with pytest.raises(ValueError, match="provenance"):
        ChecklistSourceAuthority("An unrelated source.", source_item())
    authority = ChecklistSourceAuthority(SOURCE, source_item())
    with pytest.raises(ValueError, match="differs from source authority"):
        ChecklistReconciliationRequest("project", "OTHER", source_item().text, [], source_authority=authority)


@pytest.mark.asyncio
async def test_same_source_resume_reuses_proof_but_changed_source_cannot_reuse_yes():
    from core.development.reconciliation_response import ReconciliationFailure
    gateway = FakeReasoningGateway([{
        "answer": "YES", "selected_test_names": [accepted(1).test_name], "rationale": "Controlled proof."}])
    catalog = VerifiedCatalog()
    progress = []
    result = await RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
        RoutedChecklistRequest("project", source_item(), SOURCE, [accepted(1)],
            checkpoint=lambda value: progress.append(value), language_id="python"))
    saved = progress[-1]
    restored = SpecificationChecklistItem.from_dict(json.loads(json.dumps(source_item().to_dict())))
    resumed_gateway = FakeReasoningGateway([])
    reconciler = RoutedChecklistReconciler(ChecklistItemReconciler(resumed_gateway, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),)))
    same = await reconciler.reconcile(RoutedChecklistRequest("project", restored, SOURCE,
        [accepted(1)], progress=saved, language_id="python"))
    assert same == result and not resumed_gateway.requests
    with pytest.raises(ReconciliationFailure, match="identity"):
        await reconciler.reconcile(RoutedChecklistRequest("project", restored,
            SOURCE + " Deletion is not required.", [accepted(1)], progress=saved, language_id="python"))
    assert not resumed_gateway.requests


@pytest.mark.asyncio
async def test_legacy_cached_yes_without_source_authority_cannot_bypass_new_review():
    from core.development.specification_reconciliation import ChecklistReconciliationRequest
    from core.development.reconciliation_response import ReconciliationFailure
    gateway = FakeReasoningGateway([{
        "answer": "YES", "selected_test_names": [accepted(1).test_name], "rationale": "Legacy proof."}])
    catalog = VerifiedCatalog()
    progress = []
    await ChecklistItemReconciler(gateway, catalog).reconcile(ChecklistReconciliationRequest(
        "project", source_item().ref, source_item().text, [accepted(1)],
        checkpoint=lambda value: progress.append(value)))
    resumed = FakeReasoningGateway([])
    with pytest.raises(ReconciliationFailure, match="identity"):
        await RoutedChecklistReconciler(ChecklistItemReconciler(resumed, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
            RoutedChecklistRequest("project", source_item(), SOURCE, [accepted(1)], progress=progress[-1], language_id="python"))
    assert not resumed.requests


@pytest.mark.asyncio
async def test_existing_typed_source_clause_preserves_the_same_authority():
    from core.development.specification_domain import SourceRequirementClause
    clause = SourceRequirementClause("COUNT", source_item().text, "behavior", "test",
        QUOTE, "adds exactly one entry")
    gateway = FakeReasoningGateway([response()])
    catalog = VerifiedCatalog()
    await RoutedChecklistReconciler(ChecklistItemReconciler(gateway, catalog), catalog, adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
        RoutedChecklistRequest("project", clause, SOURCE, [accepted(1)], language_id="python"))
    authority = json.loads(gateway.requests[0].prompt)["specification_authority"]
    assert authority["original_source"] == SOURCE
    assert authority["selected_item"] == clause.to_dict()
