"""Final functional API evidence derives only from original source."""
from __future__ import annotations

from core.development.required_public_signature import RequiredPublicSignature, required_signatures
from core.development.specification_evidence_policy import SpecificationEvidenceAdapter
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import SpecificationSnapshot


def signature_evidence(source: str, snapshot: SpecificationSnapshot, adapter: SpecificationEvidenceAdapter | None) -> dict[str, object] | None:
    signatures = required_signatures(source)
    if not signatures:
        return None
    failed: list[str] = []
    unknown: list[str] = []
    deferred: list[RequiredPublicSignature] = []
    violated: list[RequiredPublicSignature] = []
    if adapter is None:
        unknown.append("required public signature has no language evidence adapter")
    else:
        try:
            proof = adapter.signature_assurance(snapshot, signatures)
            failed.extend(proof.violations)
            unknown.extend(proof.unsupported)
            deferred.extend(proof.deferred_to_naming)
            violated.extend(proof.violated_signatures)
        except SyntaxError:
            unknown.append("required public signature cannot be proven from malformed source")
    if not snapshot.complete:
        unknown.append("required public signature snapshot is incomplete")
    findings = failed + unknown
    naming_only = bool(deferred) and not findings
    remaining = signatures if unknown and adapter is not None and snapshot.complete else violated
    return {
        "checklist_ref": "source-required-public-signatures", "answer": "NO" if findings else "NOT_APPLICABLE" if naming_only else "YES",
        "accepted_test_names": [], "evidence_policy": "source_public_signature",
        "evidence_status": "fail" if failed else "unsupported_evidence_policy" if unknown else "deferred_to_naming" if naming_only else "pass",
        "revision": snapshot.revision, "findings": findings,
        "rationale": "Existing source-bound call shapes checked at the canonical revision; lexical identifiers reconcile in Naming.",
        "required_signatures": [item.to_dict() for item in signatures],
        "deferred_signatures": [item.to_dict() for item in deferred],
        "remaining_obligations": [SpecificationChecklistItem(
            "call-" + item.name, "Calling " + item.source_quote, "behavior",
            source_quote=item.source_quote, subject=item.source_quote).to_dict() for item in remaining],
        "snapshot_complete": snapshot.complete,
        "failed_signatures": [item.to_dict() for item in violated],
        "unsupported_findings": unknown,
    }
