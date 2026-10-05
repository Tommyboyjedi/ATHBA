"""Conservative conjunctive decomposition; no partial compound approval."""
from __future__ import annotations

import re
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import EvidencePolicyRouter
from core.development.specification_obligations import EvidencePolicy


def mechanical_compound(item: SpecificationChecklistItem) -> bool:
    return (item.kind in {"constraint", "quality"}
            and EvidencePolicyRouter().route(item).policy == EvidencePolicy.UNSUPPORTED
            and bool(re.search(r",|\band\b|\bor\b", item.subject)))


def validate_mechanical_children(parent: SpecificationChecklistItem, children: tuple[SpecificationChecklistItem, ...]) -> None:
    if not mechanical_compound(parent):
        return
    if re.search(r"\bor\b", parent.subject):
        raise ValueError("disjunctive mechanical obligation cannot be partitioned conjunctively")
    subjects = tuple(part.strip().casefold() for part in
                     re.split(r",\s*(?:and\s+)?|\s+and\s+", parent.subject))
    supplied = tuple(child.subject.strip().casefold() for child in children)
    if len(subjects) < 2 or len(set(subjects)) != len(subjects) or sorted(supplied) != sorted(subjects):
        raise ValueError("mechanical children must partition every parent conjunct exactly once")
    policies = {EvidencePolicy.DEPENDENCY, EvidencePolicy.STORAGE, EvidencePolicy.PUBLIC_SURFACE}
    for child in children:
        if child.modality != parent.modality or child.kind != parent.kind:
            raise ValueError("mechanical child must preserve parent kind and modality")
        if child.source_quote != parent.source_quote:
            raise ValueError("mechanical child must retain the same parent source passage")
        if EvidencePolicyRouter().route(child).policy not in policies:
            raise ValueError("mechanical child has no independent bounded verification policy")
