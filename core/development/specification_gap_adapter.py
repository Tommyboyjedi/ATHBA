from __future__ import annotations

import re
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

_MATCHING_STOPWORDS = {
    "a", "an", "and", "are", "be", "can", "for", "has", "have", "id", "ids",
    "in", "is", "must", "of", "on", "or", "shall", "that", "the", "to", "with",
}


def matching_contract_source_refs_for_gap(contract: BehaviorContract, gap: SpecificationGap) -> list[str]:
    refs = _matching_contract_source_refs(contract, gap.checklist_ref, gap.obligation_text)
    if refs:
        return refs
    raise ValueError(f"unable to trace specification gap to contract source clauses: {gap.checklist_ref}")


def matching_contract_source_refs_for_clause(
    contract: BehaviorContract,
    item: SpecificationChecklistItem | SourceRequirementClause,
) -> set[str]:
    return set(_matching_contract_source_refs(contract, item.ref, item.text))


def next_gap_requirement_ref(contract: BehaviorContract, checklist_ref: str) -> str:
    prefix = f"GK-{checklist_ref}-"
    existing = {requirement.ref for requirement in contract.observable_requirements}
    counter = 1
    while f"{prefix}{counter}" in existing:
        counter += 1
    return f"{prefix}{counter}"


def normalize_clause_text(text: str) -> str:
    return " ".join(text.lower().split())


def _matching_contract_source_refs(
    contract: BehaviorContract,
    checklist_ref: str,
    obligation_text: str,
) -> list[str]:
    direct_match = [clause.ref for clause in contract.source_clauses if clause.ref == checklist_ref]
    if direct_match:
        return direct_match
    normalized_gap_text = normalize_clause_text(obligation_text)
    text_matches = [
        clause.ref for clause in contract.source_clauses if normalize_clause_text(clause.text) == normalized_gap_text
    ]
    if text_matches:
        return text_matches
    return _matching_requirement_source_refs(contract, obligation_text)


def _matching_requirement_source_refs(contract: BehaviorContract, obligation_text: str) -> list[str]:
    best_refs: list[str] = []
    best_score = 0
    ambiguous = False
    gap_tokens = _matching_tokens(obligation_text)
    clause_texts = {clause.ref: clause.text for clause in contract.source_clauses}
    for requirement in contract.observable_requirements:
        score = _matching_requirement_score(requirement, gap_tokens, clause_texts)
        if score > best_score:
            best_score = score
            best_refs = list(requirement.source_refs)
            ambiguous = False
            continue
        if score == best_score and score >= 2 and list(requirement.source_refs) != best_refs:
            ambiguous = True
    if best_score < 2 or ambiguous:
        return []
    return best_refs


def _matching_requirement_score(
    requirement: BehaviorContractRequirement,
    gap_tokens: set[str],
    clause_texts: dict[str, str],
) -> int:
    source_text = " ".join(clause_texts.get(ref, "") for ref in requirement.source_refs)
    requirement_tokens = _matching_tokens(
        " ".join((requirement.summary, requirement.observable_outcome, source_text))
    )
    return len(gap_tokens.intersection(requirement_tokens))


def _matching_tokens(text: str) -> set[str]:
    tokens = set()
    for raw in re.findall(r"[a-z0-9]+", text.lower()):
        token = _normalize_match_token(raw)
        if token and token not in _MATCHING_STOPWORDS:
            tokens.add(token)
    return tokens


def _normalize_match_token(token: str) -> str:
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif len(token) > 3 and token.endswith("ed"):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("s"):
        token = token[:-1]
    return token


def _gap_error_expectation(gap: SpecificationGap) -> str | None:
    if gap.item_kind != ChecklistItemKind.VALIDATION.value:
        return None
    return "Add executable proof for the missing validation outcome."
