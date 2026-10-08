"""Behavioral completion and assurance confidence are independent."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re

from core.development.required_public_signature import RequiredPublicSignature, required_signatures
from core.development.source_obligation_semantics import ObligationType
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import EvidencePolicyRouter, EvidenceStatus, reconciliation_satisfied
from core.development.specification_obligations import EvidencePolicy


class AssuranceOutcome(str, Enum):
    PROVEN = "proven"
    VIOLATED = "violated"
    UNPROVEN = "unproven"


@dataclass(frozen=True)
class AssuranceGap:
    checklist_ref: str
    policy: str
    revision: str
    diagnostic: str

    def __post_init__(self) -> None:
        if not all(isinstance(x, str) and x.strip() for x in
                   (self.checklist_ref, self.policy, self.revision, self.diagnostic)):
            raise ValueError("assurance gap requires retained source, policy, revision and diagnosis")
        if re.fullmatch(r"[0-9a-f]{40}", self.revision) is None:
            raise ValueError("assurance gap requires an exact evidence revision")


@dataclass(frozen=True)
class CompletionAuthority:
    records: tuple[dict[str, object], ...]
    original_source: str


@dataclass(frozen=True)
class CompletionAssessment:
    behaviorally_complete: bool
    unproven_assurance: tuple[AssuranceGap, ...] = ()

    @property
    def fully_proven(self) -> bool:
        return self.behaviorally_complete and not self.unproven_assurance


def assess_completion(authority: CompletionAuthority) -> CompletionAssessment:
    active = [record for record in authority.records if record.get("status") != "superseded"]
    if not active:
        return CompletionAssessment(False)
    gaps = []
    for record in active:
        if reconciliation_satisfied((record,)) or domain_covered(record, authority.original_source):
            continue
        gap = unproven_gap(record, authority.original_source)
        if gap is None:
            return CompletionAssessment(False)
        gaps.append(gap)
    return CompletionAssessment(True, tuple(gaps))


def unproven_gap(record: dict[str, object], source: str) -> AssuranceGap | None:
    if (record.get("answer") != "NO" or record.get("evidence_status") != EvidenceStatus.UNSUPPORTED.value
            or record.get("status") or record.get("blocked_reason")):
        return None
    try:
        if record.get("evidence_policy") == "source_public_signature":
            entries = record.get("required_signatures")
            if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
                return None
            declared = tuple(RequiredPublicSignature.from_dict(item) for item in entries)
            if not declared or declared != required_signatures(source):
                return None
        else:
            payload = record.get("source_item")
            if not isinstance(payload, dict):
                return None
            item = SpecificationChecklistItem.from_dict(payload)
            decision = EvidencePolicyRouter().route_source(item, source)
            if (item.ref != record.get("checklist_ref") or not item.source_quote
                    or item.obligation_type not in {ObligationType.MECHANICAL.value, ObligationType.NON_PERSISTENCE.value}
                    or decision.policy.value != record.get("evidence_policy")
                    or decision.policy not in {EvidencePolicy.DEPENDENCY, EvidencePolicy.STORAGE,
                                               EvidencePolicy.QUALITY, EvidencePolicy.PUBLIC_SURFACE}):
                return None
        return AssuranceGap(str(record["checklist_ref"]), str(record["evidence_policy"]),
                            str(record["revision"]), str(record["rationale"]))
    except (ValueError, KeyError, TypeError):
        return None

def domain_covered(record: dict[str, object], source: str) -> bool:
    if (record.get("answer") != "NOT_APPLICABLE"
            or record.get("evidence_policy") != EvidencePolicy.DOMAIN.value
            or record.get("evidence_status") != EvidenceStatus.DOMAIN.value
            or record.get("findings") != []):
        return False
    payload = record.get("source_item")
    if not isinstance(payload, dict):
        return False
    try:
        item = SpecificationChecklistItem.from_dict(payload)
        return (item.ref == record.get("checklist_ref") and bool(item.source_quote)
                and EvidencePolicyRouter().route_source(item, source).policy == EvidencePolicy.DOMAIN)
    except (ValueError, KeyError, TypeError):
        return False
