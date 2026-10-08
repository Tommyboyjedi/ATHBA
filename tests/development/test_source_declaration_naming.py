"""Source-declared class identifiers are retained for late Naming, not static quality."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.development.behavior_contract_coordinator import RequirementClausePlanner
from core.development.source_obligation_semantics import ObligationType
from core.development.specification_domain import SourceRequirementClause
from core.development.post_behavior_adapters import focused_naming_material
from core.execution.reasoning_gateway import ReasoningResult


@pytest.mark.asyncio
async def test_actual_named_class_source_response_is_valid_without_correction():
    fixture = json.loads((Path(__file__).parent / "fixtures/shoppingbasket_named_class_source_draft.json").read_text())
    class Gateway:
        def __init__(self):
            self.requests = []
        async def reason(self, request):
            self.requests.append(request)
            return ReasoningResult(json.dumps(fixture["draft"]))
    gateway = Gateway()
    clauses = await RequirementClausePlanner(gateway).create_clauses(
        project_id="retained-naming", requirement_text=fixture["requirement_text"])
    assert len(gateway.requests) == 1
    named = clauses[0]
    assert named.obligation_type == ObligationType.NAMING.value
    assert named.evidence_kind == "review"
    assert any(c.obligation_type == ObligationType.PRECONDITION.value for c in clauses)


@pytest.mark.parametrize("verb", ["Provide", "Implement", "Define"])
def test_explicit_source_class_declaration_grounds_late_naming(verb):
    quote = f"{verb} a Ledger class in ledger.module"
    clause = SourceRequirementClause("S1", quote, "quality", "review", quote, "Ledger class", "naming")
    clause.source_context(quote)
    delivery = SimpleNamespace(contract=SimpleNamespace(
        public_api=(), source_clauses=(clause,), requirement_source=quote))
    assert "Ledger" in focused_naming_material(delivery).required_identifiers


def test_naming_classification_cannot_be_inferred_from_ungrounded_class_text():
    with pytest.raises(ValueError):
        SourceRequirementClause("S1", "Provide a Ledger class", "quality", "review",
            "Maintain all totals in memory", "Ledger class", "naming")


def test_persistence_subject_does_not_inherit_adjacent_class_naming():
    quote = "Provide a Ledger class and keep all state in memory"
    clause = SourceRequirementClause("S1", "Keep state in memory", "constraint", "mechanical",
        quote, "state", "non_persistence_assurance")
    clause.source_context(quote)
    assert clause.obligation_type == ObligationType.NON_PERSISTENCE.value
