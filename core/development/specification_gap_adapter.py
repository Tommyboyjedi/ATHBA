from __future__ import annotations

from dataclasses import replace

from core.development.tdd_progression import BehaviorContract, BehaviorContractRequirement, SourceRequirementClause, SpecificationChecklistItem, SpecificationGap
from core.development.tdd_progression_values import ChecklistItemKind


class SpecificationGapTddAdapter:
    """Turn one targeted specification gap into one supplemental contract requirement."""

    def extend_contract_for_gap(self, contract: BehaviorContract, gap: SpecificationGap) -> BehaviorContract:
        prefix = f"GK-{gap.checklist_ref}-"
        if any(requirement.ref.startswith(prefix) for requirement in contract.observable_requirements):
            return contract
        requirement = BehaviorContractRequirement(
            ref=next_gap_requirement_ref(contract, gap.checklist_ref),
            source_refs=matching_contract_source_refs_for_gap(contract, gap),
            summary=gap.obligation_text,
            observable_outcome=gap.desired_proof,
            test_hint=gap.desired_proof,
            error_expectation=_gap_error_expectation(gap),
            preserves_state_on_failure=gap.item_kind in _STATE_PRESERVING_KINDS,
        )
        return replace(
            contract,
            observable_requirements=[*contract.observable_requirements, requirement],
        )


_STATE_PRESERVING_KINDS = {
    ChecklistItemKind.VALIDATION.value,
    ChecklistItemKind.INVARIANT.value,
    ChecklistItemKind.CONSTRAINT.value,
}


def matching_contract_source_refs_for_gap(contract: BehaviorContract, gap: SpecificationGap) -> list[str]:
    direct_match = [clause.ref for clause in contract.source_clauses if clause.ref == gap.checklist_ref]
    if direct_match:
        return direct_match
    normalized_gap_text = normalize_clause_text(gap.obligation_text)
    text_matches = [
        clause.ref for clause in contract.source_clauses if normalize_clause_text(clause.text) == normalized_gap_text
    ]
    if text_matches:
        return text_matches
    raise ValueError(f"unable to trace specification gap to contract source clauses: {gap.checklist_ref}")


def matching_contract_source_refs_for_clause(
    contract: BehaviorContract,
    item: SpecificationChecklistItem | SourceRequirementClause,
) -> set[str]:
    direct_match = {clause.ref for clause in contract.source_clauses if clause.ref == item.ref}
    if direct_match:
        return direct_match
    normalized_item_text = normalize_clause_text(item.text)
    return {clause.ref for clause in contract.source_clauses if normalize_clause_text(clause.text) == normalized_item_text}


def next_gap_requirement_ref(contract: BehaviorContract, checklist_ref: str) -> str:
    prefix = f"GK-{checklist_ref}-"
    existing = {requirement.ref for requirement in contract.observable_requirements}
    counter = 1
    while f"{prefix}{counter}" in existing:
        counter += 1
    return f"{prefix}{counter}"


def normalize_clause_text(text: str) -> str:
    return " ".join(text.lower().split())


def _gap_error_expectation(gap: SpecificationGap) -> str | None:
    if gap.item_kind != ChecklistItemKind.VALIDATION.value:
        return None
    return "Add executable proof for the missing validation outcome."
