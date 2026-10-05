"""Source signature checks use the existing language evidence capability boundary."""
from __future__ import annotations

from core.development.required_public_signature import SignatureInspection
from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_evidence_policy import SpecificationEvidenceAdapters


def signature_adapter(language_id: str):
    return SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),)).for_language(language_id)


def production_signature_findings(request: SignatureInspection, language_id: str) -> tuple[str, ...]:
    adapter = signature_adapter(language_id)
    if adapter is None:
        return ("required public signature has no language evidence adapter",)
    return adapter.verify_public_signatures(request)


def scenario_signature_findings(request: SignatureInspection, language_id: str) -> tuple[str, ...]:
    if not request.signatures:
        return ()
    adapter = signature_adapter(language_id)
    if adapter is None:
        return ("required public signature has no language evidence adapter",)
    return adapter.verify_scenario_signatures(request)
