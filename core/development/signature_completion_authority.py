"""Only explicit lexical deferral can cross the late Naming boundary."""
from __future__ import annotations

import re

from core.development.required_public_signature import RequiredPublicSignature, required_signatures
from core.development.specification_evidence_policy import EvidenceStatus


def naming_signature_deferred(record: dict[str, object], source: str) -> bool:
    if (record.get("answer") != "NOT_APPLICABLE"
            or record.get("evidence_status") != EvidenceStatus.NAMING.value
            or record.get("checklist_ref") != "source-required-public-signatures"
            or record.get("findings") != [] or record.get("status") or record.get("blocked_reason")
            or re.fullmatch(r"[0-9a-f]{40}", str(record.get("revision", ""))) is None):
        return False
    try:
        declared = _signatures(record.get("required_signatures"))
        deferred = _signatures(record.get("deferred_signatures"))
        return (bool(declared) and declared == required_signatures(source) and bool(deferred)
                and len(set(deferred)) == len(deferred) and set(deferred) <= set(declared))
    except (ValueError, KeyError, TypeError):
        return False


def _signatures(value: object) -> tuple[RequiredPublicSignature, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("signature authority requires exact structured source entries")
    return tuple(RequiredPublicSignature.from_dict(item) for item in value)
