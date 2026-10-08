"""Final functional API evidence derives only from original source."""
from __future__ import annotations

from core.development.required_public_signature import required_signatures
from core.development.public_signature_validation import signature_adapter
from core.development.specification_evidence_policy import SpecificationSnapshot


def signature_evidence(source: str, snapshot: SpecificationSnapshot, language_id: str) -> dict[str, object] | None:
    signatures = required_signatures(source)
    if not signatures:
        return None
    findings: list[str] = []
    adapter = signature_adapter(language_id)
    if adapter is None:
        findings.append("required public signature has no language evidence adapter")
    else:
        try:
            findings.extend(adapter.verify_signature_snapshot(snapshot, signatures))
        except SyntaxError:
            findings.append("required public signature cannot be proven from malformed source")
    if not snapshot.complete:
        findings.append("required public signature snapshot is incomplete")
    return {
        "checklist_ref": "source-required-public-signatures", "answer": "NO" if findings else "YES",
        "accepted_test_names": [], "evidence_policy": "source_public_signature",
        "revision": snapshot.revision, "findings": findings,
        "rationale": "Existing source-bound call shapes checked at the canonical revision; lexical identifiers reconcile in Naming.",
        "required_signatures": [item.to_dict() for item in signatures],
    }
