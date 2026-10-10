"""Final functional API evidence derives only from original source."""
from __future__ import annotations

from core.development.required_public_signature import required_signatures
from core.development.public_signature_validation import signature_adapter
from core.development.specification_evidence_policy import SpecificationSnapshot


def signature_evidence(source: str, snapshot: SpecificationSnapshot, language_id: str) -> dict[str, object] | None:
    signatures = required_signatures(source)
    if not signatures:
        return None
    failed, unknown, deferred = [], [], []
    adapter = signature_adapter(language_id)
    if adapter is None:
        unknown.append("required public signature has no language evidence adapter")
    else:
        try:
            proof = adapter.signature_assurance(snapshot, signatures)
            failed.extend(proof.violations)
            unknown.extend(proof.unsupported)
            deferred.extend(proof.deferred_to_naming)
        except SyntaxError:
            unknown.append("required public signature cannot be proven from malformed source")
    if not snapshot.complete:
        unknown.append("required public signature snapshot is incomplete")
    findings = failed + unknown
    naming_only = bool(deferred) and not findings
    return {
        "checklist_ref": "source-required-public-signatures", "answer": "NO" if findings else "NOT_APPLICABLE" if naming_only else "YES",
        "accepted_test_names": [], "evidence_policy": "source_public_signature",
        "evidence_status": "fail" if failed else "unsupported_evidence_policy" if unknown else "deferred_to_naming" if naming_only else "pass",
        "revision": snapshot.revision, "findings": findings,
        "rationale": "Existing source-bound call shapes checked at the canonical revision; lexical identifiers reconcile in Naming.",
        "required_signatures": [item.to_dict() for item in signatures],
        "deferred_signatures": [item.to_dict() for item in deferred],
    }
