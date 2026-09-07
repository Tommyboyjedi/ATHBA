"""Typed evidence decisions and outcomes, independent of language inspection."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from core.development.microcycle_domain import LanguageAdapterDescriptor
from core.development.specification_domain import SourceRequirementClause, SpecificationChecklistItem
from core.development.specification_obligations import EvidencePolicy, ObligationModality, explicit_modality

ChecklistItem = SpecificationChecklistItem | SourceRequirementClause
ENGINEERING_PROFILE_QUALITIES = frozenset({"small", "direct", "readable"})


class EvidenceStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNSUPPORTED = "unsupported_evidence_policy"
    NOT_REQUIRED = "not_required"
    ENGINEERING_COVERED = "covered_by_engineering_policy"


@dataclass(frozen=True)
class EvidenceDecision:
    policy: EvidencePolicy
    subject: str
    modality: ObligationModality
    scope_permitted: bool = False
    required_subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceResult:
    status: EvidenceStatus
    policy: EvidencePolicy
    revision: str
    details: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()

    def to_record(self, item: ChecklistItem) -> dict[str, object]:
        answer = "YES" if self.status == EvidenceStatus.PASS else "NO"
        if self.status in {EvidenceStatus.NOT_REQUIRED, EvidenceStatus.ENGINEERING_COVERED}:
            answer = "NOT_APPLICABLE"
        return {"checklist_ref": item.ref, "answer": answer,
                "accepted_test_names": [], "rationale": "; ".join(self.details),
                "evidence_policy": self.policy.value, "evidence_status": self.status.value,
                "revision": self.revision, "findings": list(self.findings),
                "source_item": item.to_dict(), "response_attempts": []}


@dataclass(frozen=True)
class RevisionFile:
    path: str
    source: str


@dataclass(frozen=True)
class SpecificationSnapshot:
    revision: str
    files: tuple[RevisionFile, ...]
    complete: bool = True
    diagnostics: tuple[str, ...] = ()


class SpecificationEvidenceAdapter(Protocol):
    descriptor: LanguageAdapterDescriptor

    def verify(self, decision: EvidenceDecision, snapshot: SpecificationSnapshot) -> EvidenceResult: ...


@dataclass(frozen=True)
class SpecificationEvidenceAdapters:
    adapters: tuple[SpecificationEvidenceAdapter, ...]

    def for_language(self, language_id: str) -> SpecificationEvidenceAdapter | None:
        matches = [item for item in self.adapters if item.descriptor.language_id == language_id]
        return matches[0] if len(matches) == 1 else None


class EvidencePolicyRouter:
    """One centralized wording boundary; verifiers never interpret specification prose."""

    def route(self, item: ChecklistItem) -> EvidenceDecision:
        quote = getattr(item, "source_quote", "") or item.text
        modality = explicit_modality(quote) or ObligationModality(getattr(item, "modality", "required"))
        subject = (getattr(item, "subject", "") or item.text).lower()
        policy = _policy(item.kind, modality, subject)
        if policy != EvidencePolicy.UNSUPPORTED and modality == ObligationModality.FORBIDDEN and re.search(r"\bexpose\b|\bimplement\b|\bexist\b", quote.lower()):
            policy = EvidencePolicy.PUBLIC_SURFACE
        return EvidenceDecision(policy, subject, modality, bool(re.search(r"\boptional\b", quote.lower())))

def _policy(kind: str, modality: ObligationModality, subject: str) -> EvidencePolicy:
    if modality == ObligationModality.NON_GOAL:
        return EvidencePolicy.NON_GOAL
    if kind in {"constraint", "quality"} and re.search(r",|\band\b|\bor\b", subject):
        return EvidencePolicy.UNSUPPORTED
    if re.search(r'\bdependency[- ]free\b|\bno external dependencies\b', subject):
        return EvidencePolicy.DEPENDENCY if modality == ObligationModality.REQUIRED else EvidencePolicy.UNSUPPORTED
    if re.search(r'\bin[- ]memory\b|\bpersist\w*\b|\bstorage\b', subject):
        return EvidencePolicy.STORAGE
    if modality == ObligationModality.FORBIDDEN and kind in {"constraint", "quality"}:
        return EvidencePolicy.PUBLIC_SURFACE
    if kind == "quality" and modality == ObligationModality.REQUIRED and subject.strip() in ENGINEERING_PROFILE_QUALITIES:
        return EvidencePolicy.ENGINEERING
    if kind in {"constraint", "quality"}:
        return EvidencePolicy.QUALITY
    return EvidencePolicy.BEHAVIORAL

def reconciliation_satisfied(records: tuple[dict[str, object], ...]) -> bool:
    return bool(records) and all(
        item.get("answer") == "YES" or (
            item.get("answer") == "NOT_APPLICABLE"
            and item.get("evidence_policy") == EvidencePolicy.NON_GOAL.value
            and item.get("evidence_status") == EvidenceStatus.NOT_REQUIRED.value
            and item.get("findings") == []
        ) or engineering_policy_covered(item) for item in records
    )


def engineering_policy_covered(record: dict[str, object]) -> bool:
    """Accept only the explicit delegation record, never arbitrary NOT_APPLICABLE."""
    if not (
        record.get("answer") == "NOT_APPLICABLE"
        and record.get("evidence_policy") == EvidencePolicy.ENGINEERING.value
        and record.get("evidence_status") == EvidenceStatus.ENGINEERING_COVERED.value
        and record.get("findings") == []
        and record.get("accepted_test_names") == []
        and record.get("response_attempts") == []
    ):
        return False
    source = record.get("source_item")
    if not isinstance(source, dict) or source.get("modality") != ObligationModality.REQUIRED.value:
        return False
    try:
        item = SpecificationChecklistItem.from_dict(source)
        return (
            item.ref == record.get("checklist_ref")
            and bool(item.source_quote)
            and bool(item.subject)
            and bool(re.search(r"\b" + re.escape(item.subject.lower()) + r"\b", item.source_quote.lower()))
            and EvidencePolicyRouter().route(item).policy == EvidencePolicy.ENGINEERING
        )
    except (KeyError, TypeError, ValueError):
        return False
