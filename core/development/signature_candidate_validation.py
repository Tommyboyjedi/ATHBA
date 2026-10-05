"""ATHBA-owned candidate validation before trusted revision progression."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from core.development.required_public_signature import RequiredPublicSignature, SignatureInspection, SIGNATURE_MISMATCH
from core.development.public_signature_validation import production_signature_findings
from core.execution.work_unit_gateway import WorkUnitExecutionResult


@dataclass(frozen=True)
class SignatureCandidateContext:
    repository: Path
    production_path: str
    signatures: tuple[RequiredPublicSignature, ...]
    language_id: str


def validate_signature_candidate(context: SignatureCandidateContext, result: WorkUnitExecutionResult) -> WorkUnitExecutionResult:
    if not result.accepted or not result.accepted_revision or not context.signatures:
        return result
    try:
        source = subprocess.run(
            ["git", "show", f"{result.accepted_revision}:{context.production_path}"],
            cwd=context.repository, check=True, capture_output=True, text=True,
        ).stdout
        findings = production_signature_findings(SignatureInspection(source, context.signatures), context.language_id)
    except (subprocess.CalledProcessError, SyntaxError) as error:
        findings = (f"{SIGNATURE_MISMATCH}: candidate signature could not be established ({type(error).__name__})",)
    if not findings:
        return result
    return replace(result, accepted=False, status=SIGNATURE_MISMATCH,
                   accepted_revision=None, error=f"candidate_revision={result.accepted_revision}; " + "; ".join(findings))
