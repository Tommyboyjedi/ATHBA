"""Lexical uncertainty must reach existing Naming, never become behavioral failure."""
from core.development.python_parameter_naming import PythonParameterNaming
from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_evidence_policy import SpecificationEvidenceAdapters
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.development.assurance_completion import CompletionAuthority, assess_completion
from core.development.feature_signature_evidence import signature_evidence
from core.development.post_behavior_assessment import (
    NamingAssessmentInput, NamingMaterial, parse_naming_decision,
)
from core.development.post_behavior_slice import FocusedProductionSlice, ProductionSliceScope
from core.development.required_public_signature import required_signatures
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import EvidenceStatus, RevisionFile, SpecificationSnapshot
from core.development.specification_evidence_routing import RoutedChecklistReconciler, RoutedChecklistRequest

REVISION = "a" * 40
SOURCE = "Provide a Counter class. Calling total() returns the current total."


def snapshot(code):
    return SpecificationSnapshot(REVISION, (RevisionFile("counter.py", code),))


def naming(code):
    signatures = required_signatures(SOURCE)
    return NamingAssessmentInput(NamingMaterial(SOURCE, ("Counter", "total"), signatures),
        FocusedProductionSlice(REVISION, (RevisionFile("counter.py", code),),
            ProductionSliceScope("b" * 40, REVISION, ("counter.py",))), parameter_naming=PythonParameterNaming())


@pytest.mark.parametrize("code", [
    "class Counter:\n    def get_total(self): return 3\n",
    "class Meter:\n    def total(self): return 3\n",
])
def test_missing_source_spelling_is_uncertainty_not_proven_call_shape_violation(code):
    result = signature_evidence(SOURCE, snapshot(code), PythonSpecificationEvidenceAdapter())
    assert result["answer"] == "NOT_APPLICABLE"
    assert result["evidence_status"] == EvidenceStatus.NAMING.value
    completion = assess_completion(CompletionAuthority(({"answer": "YES"}, result), SOURCE))
    assert completion.behaviorally_complete
    assert completion.fully_proven
    with pytest.raises(ValueError, match="operation naming mismatch"):
        parse_naming_decision("NO", naming(code))


def test_late_operation_rename_restores_signature_proof():
    before = "class Counter:\n    def get_total(self): return 3\n"
    decision = parse_naming_decision("YES\ncurrent_name: get_total\nrequired_name: total", naming(before))
    assert decision.rename.current_name == "get_total"
    after = "class Counter:\n    def total(self): return 3\n"
    assert signature_evidence(SOURCE, snapshot(after), PythonSpecificationEvidenceAdapter())["answer"] == "YES"
    assert parse_naming_decision("NO", naming(after)).rename is None


def test_actual_wrong_call_shape_still_blocks_behavioral_completion():
    bad = "class Counter:\n    def total(self, other=0): return 3\n"
    result = signature_evidence(SOURCE, snapshot(bad), PythonSpecificationEvidenceAdapter())
    assert result["evidence_status"] == EvidenceStatus.FAIL.value
    assert not assess_completion(CompletionAuthority(({"answer": "YES"}, result), SOURCE)).behaviorally_complete


def test_ambiguous_declarations_are_not_a_proven_runtime_violation():
    code = "class Counter:\n    def total(self, other): return 3\n    def total(self): return 3\n"
    assert signature_evidence(SOURCE, snapshot(code), PythonSpecificationEvidenceAdapter())["evidence_status"] == EvidenceStatus.UNSUPPORTED.value


class NoBehavioralOrMechanicalCall:
    async def reconcile(self, request):
        raise AssertionError("Lexical authority belongs to Naming, not behavioral review")


def naming_item():
    source = "The operation must be named balance."
    return source, SpecificationChecklistItem("NAME", source, "constraint",
        source_quote=source, subject="named balance")


@pytest.mark.asyncio
async def test_typed_lexical_obligation_is_deferred_to_naming_without_claiming_proof():
    source, item = naming_item()
    reconciler = RoutedChecklistReconciler(NoBehavioralOrMechanicalCall(),
        SimpleNamespace(semantic_revision=REVISION), adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),)))
    result = await reconciler.reconcile(RoutedChecklistRequest("project", item, source, [], language_id="python"))
    assert result["answer"] == "NOT_APPLICABLE"
    assert result["evidence_policy"] == "post_behavior_naming"
    assert result["evidence_status"] == "deferred_to_naming"
    assert result["source_item"] == item.to_dict()
    assert assess_completion(CompletionAuthority(({"answer": "YES"}, result), source)).fully_proven


@pytest.mark.asyncio
async def test_deferred_lexical_record_cannot_cover_behavior_or_invalid_source():
    source, item = naming_item()
    result = await RoutedChecklistReconciler(NoBehavioralOrMechanicalCall(),
        SimpleNamespace(semantic_revision=REVISION), adapters=SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))).reconcile(
            RoutedChecklistRequest("project", item, source, [], language_id="python"))
    assert not assess_completion(CompletionAuthority((result,), "A different source.")).behaviorally_complete
    behavioral = SpecificationChecklistItem("NAME", "Returns the current balance.", "behavior",
        source_quote="Returns the current balance.", subject="current balance")
    fake = {**result, "source_item": behavioral.to_dict()}
    assert not assess_completion(CompletionAuthority((fake,), "Returns the current balance.")).behaviorally_complete
    assert not assess_completion(CompletionAuthority(({**result, "findings": ["unresolved"]},), source)).behaviorally_complete

def test_naming_no_cannot_ignore_explicit_non_signature_identifier():
    request = naming("class Counter:\n    def total(self): return 3\n")
    request = replace(request, material=replace(request.material,
        required_identifiers=("Counter", "total", "balance")))
    with pytest.raises(ValueError, match="identifier naming mismatch"):
        parse_naming_decision("NO", request)
