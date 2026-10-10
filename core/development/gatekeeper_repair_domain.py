"""Revision-bound evidence for a bounded supplemental Gatekeeper obligation."""
from __future__ import annotations

import re
from dataclasses import dataclass

from core.development.required_public_signature import RequiredPublicSignature


@dataclass(frozen=True)
class SpecificationRepairRecord:
    behavior_ref: str
    source_refs: tuple[str, ...]
    signature: RequiredPublicSignature
    canonical_revision: str
    reconciliation: tuple[dict[str, object], ...]
    reconciliation_progress: tuple[dict[str, object], ...]

    def __post_init__(self) -> None:
        if not self.behavior_ref or not self.source_refs or any(not ref for ref in self.source_refs):
            raise ValueError("specification repair requires one source-grounded behavior")
        if re.fullmatch(r"[0-9a-f]{40}", self.canonical_revision) is None:
            raise ValueError("specification repair requires an exact accepted revision")
        if not self.reconciliation:
            raise ValueError("specification repair must preserve the failed reconciliation")

    def to_dict(self) -> dict[str, object]:
        return {"behavior_ref": self.behavior_ref, "source_refs": list(self.source_refs),
                "signature": self.signature.to_dict(), "canonical_revision": self.canonical_revision,
                "reconciliation": list(self.reconciliation),
                "reconciliation_progress": list(self.reconciliation_progress)}

    @classmethod
    def from_dict(cls, payload: dict) -> SpecificationRepairRecord:
        return cls(payload["behavior_ref"], tuple(payload["source_refs"]),
                   RequiredPublicSignature.from_dict(payload["signature"]), payload["canonical_revision"],
                   tuple(payload["reconciliation"]), tuple(payload["reconciliation_progress"]))
