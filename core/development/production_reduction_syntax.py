"""Language-neutral source reduction capability; no semantic inference."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
from core.development.required_public_signature import RequiredPublicSignature


@dataclass(frozen=True)
class ReductionContributionSource:
    before: bytes | None
    after: bytes | None
    selected: bool


@dataclass(frozen=True)
class ReductionSource:
    path: str
    baseline: bytes | None
    candidate: bytes | None
    contributions: tuple[ReductionContributionSource, ...] = ()
    protected_identifiers: tuple[RequiredPublicSignature, ...] = ()


@dataclass(frozen=True)
class ReductionOpportunity:
    transformation_id: str
    path: str
    replacement: bytes | None
    description: str


@dataclass(frozen=True)
class ReductionPlan:
    opportunities: tuple[ReductionOpportunity, ...] = ()
    limitations: tuple[str, ...] = ()


class ProductionReductionAdapter(Protocol):
    def plan(self, request: ReductionSource) -> ReductionPlan: ...
