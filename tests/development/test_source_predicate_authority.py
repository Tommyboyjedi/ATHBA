"""Retained source predicates must not disappear behind a narrow noun subject."""
import json
from pathlib import Path

import pytest

from core.development.behavior_contract_coordinator import RequirementClausePlanner
from core.development.source_obligation_semantics import ObligationType
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import EvidencePolicyRouter
from core.development.specification_obligations import EvidencePolicy
from core.execution.reasoning_gateway import ReasoningResult


@pytest.mark.asyncio
async def test_actual_shoppingbasket_source_draft_needs_no_correction():
    fixture = json.loads((Path(__file__).parent / "fixtures/shoppingbasket_source_clause_draft.json").read_text())
    class Gateway:
        def __init__(self):
            self.requests = []
        async def reason(self, request):
            self.requests.append(request)
            return ReasoningResult(json.dumps(fixture["draft"]))
    gateway = Gateway()
    clauses = await RequirementClausePlanner(gateway).create_clauses(
        project_id="source-predicate", requirement_text=fixture["requirement_text"])
    assert len(gateway.requests) == 1
    assert len(clauses) == 8
    assert clauses[0].obligation_type == ObligationType.NON_PERSISTENCE.value
    assert clauses[1].obligation_type == ObligationType.MECHANICAL.value
    assert clauses[4].obligation_type == ObligationType.PRECONDITION.value


def test_owned_state_noun_retains_non_persistence_predicate_and_routing():
    source = "Keep readings in memory."
    item = SpecificationChecklistItem("C", source, "constraint",
        source_quote=source, subject="readings", obligation_type="non_persistence_assurance")
    assert item.source_context(source) == source
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.STORAGE
    assert SpecificationChecklistItem.from_dict(item.to_dict()) == item
    with pytest.raises(ValueError, match="classification"):
        SpecificationChecklistItem.from_dict(item.to_dict() | {"obligation_type": "mechanical_assurance"})


def test_positive_persistence_predicate_is_not_hidden_by_a_noun_subject():
    source = "Persist records across sessions."
    item = SpecificationChecklistItem("P", source, "constraint",
        source_quote=source, subject="records", obligation_type="observable_behavior")
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.BEHAVIORAL


def test_compound_assurance_still_requires_atomic_decomposition():
    source = "Keep state and configuration in memory."
    item = SpecificationChecklistItem("C", source, "constraint",
        source_quote=source, subject="state and configuration", obligation_type="non_persistence_assurance")
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.UNSUPPORTED


def test_source_predicate_does_not_bypass_provenance():
    item = SpecificationChecklistItem("C", "Keep readings in memory.", "constraint",
        source_quote="Keep readings in memory.", subject="readings", obligation_type="non_persistence_assurance")
    with pytest.raises(ValueError, match="provenance"):
        EvidencePolicyRouter().route_source(item, "Persist readings to disk.")


def test_adjacent_assurance_does_not_reclassify_the_selected_dependency():
    source = "Keep it dependency-free and in memory."
    item = SpecificationChecklistItem("D", "Keep it dependency-free.", "constraint",
        source_quote=source, subject="dependency-free", obligation_type="mechanical_assurance")
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.DEPENDENCY


def test_adjacent_rejection_does_not_convert_the_input_domain_to_error_behavior():
    source = "Values are integers and invalid values raise DomainError."
    item = SpecificationChecklistItem("D", "Values are integers.", "validation",
        source_quote=source, subject="integers", obligation_type="precondition")
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.DOMAIN


def test_ordered_source_citation_retains_negation_during_authoritative_resolution():
    source = "The component must not expose persistence."
    quote = "The component must not ... persistence."
    item = SpecificationChecklistItem("C", quote, "constraint", modality="forbidden",
        source_quote=quote, subject="persistence", obligation_type="non_persistence_assurance")
    assert SpecificationChecklistItem.from_dict(item.to_dict()) == item
    assert EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.PUBLIC_SURFACE
