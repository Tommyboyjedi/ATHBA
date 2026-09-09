"""Deterministic structural progress checks independent of generated references."""
from __future__ import annotations

from dataclasses import dataclass
import json
import unicodedata

from core.development.specification_domain import SpecificationChecklistItem

MAX_CHECKLIST_SPLIT_DEPTH = 16
UNSPLITTABLE_REASON = "specification_gatekeeper_unsplittable"


def normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def item_structure(item: SpecificationChecklistItem) -> tuple[str, ...]:
    return tuple(normalized(value) for value in
                 (item.text, item.kind, item.modality, item.source_quote, item.subject))


def split_structure(children: tuple[SpecificationChecklistItem, ...]) -> str:
    return json.dumps(sorted(item_structure(child) for child in children), ensure_ascii=True)


@dataclass(frozen=True)
class ChecklistSplitAncestry:
    items: tuple[SpecificationChecklistItem, ...] = ()
    structures: tuple[str, ...] = ()


def rejected_split(parent: SpecificationChecklistItem, children: tuple[SpecificationChecklistItem, ...],
                   ancestry: ChecklistSplitAncestry) -> str | None:
    fingerprints = [item_structure(child) for child in children]
    if split_structure(children) in ancestry.structures:
        return "repeated_ancestor_split_structure"
    if item_structure(parent) in fingerprints:
        return "child_identical_to_parent"
    if len(fingerprints) != len(set(fingerprints)):
        return "duplicate_children"
    ancestor_items = {item_structure(item) for item in ancestry.items}
    if any(fingerprint in ancestor_items for fingerprint in fingerprints):
        return "child_repeats_ancestor"
    return None
