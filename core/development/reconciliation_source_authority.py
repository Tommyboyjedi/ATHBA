"""Independent Gatekeeper interpretation retains the exact original source."""
from __future__ import annotations

from dataclasses import dataclass

from core.development.specification_domain import SourceRequirementClause, SpecificationChecklistItem

RECONCILIATION_SOURCE_SCHEMA = "athba/checklist-source-authority/v1"


@dataclass(frozen=True)
class ChecklistSourceAuthority:
    original_source: str
    item: SpecificationChecklistItem | SourceRequirementClause

    def __post_init__(self) -> None:
        if not isinstance(self.original_source, str) or not self.original_source.strip():
            raise ValueError("Gatekeeper source authority requires the original specification")
        if not isinstance(self.item, (SpecificationChecklistItem, SourceRequirementClause)):
            raise ValueError("Gatekeeper source authority requires a typed selected item")
        if self.item.source_quote:
            self.item.source_context(self.original_source)

    def to_dict(self) -> dict[str, object]:
        return {"schema": RECONCILIATION_SOURCE_SCHEMA, "original_source": self.original_source,
                "selected_item": self.item.to_dict()}
