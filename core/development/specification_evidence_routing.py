"""Route final checklist facts before invoking any semantic reconciliation."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_evidence_policy import (
    ChecklistItem, EvidencePolicyRouter, EvidenceResult, EvidenceStatus,
    SpecificationEvidenceAdapters,
)
from core.development.specification_obligations import EvidencePolicy, ObligationModality
from core.development.specification_domain import SpecificationChecklist
from core.development.specification_reconciliation import (
    AcceptedTestEvidence, ChecklistItemReconciler, ChecklistReconciliationRequest, GitAcceptedTestCatalog,
)
from core.development.specification_revision_snapshot import GitSpecificationSnapshot


@dataclass(frozen=True)
class RoutedChecklistRequest:
    project_id: str
    item: ChecklistItem
    original_source: str
    accepted: list[AcceptedTestEvidence]
    language_id: str = "python"
    required_subjects: tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutedChecklistReconciler:
    behavioral: ChecklistItemReconciler
    catalog: GitAcceptedTestCatalog
    adapters: SpecificationEvidenceAdapters = field(default_factory=lambda: SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),)))

    async def reconcile(self, request: RoutedChecklistRequest) -> dict[str, object]:
        item = request.item
        decision = replace(EvidencePolicyRouter().route(item), required_subjects=request.required_subjects)
        quote = getattr(item, "source_quote", "")
        if (quote and quote not in request.original_source) or (
            decision.policy != EvidencePolicy.BEHAVIORAL and not quote and item.text not in request.original_source
        ):
            return EvidenceResult(EvidenceStatus.UNSUPPORTED, EvidencePolicy.UNSUPPORTED,
                                  self.catalog.semantic_revision, ("source provenance mismatch",)).to_record(item)
        if decision.policy == EvidencePolicy.ENGINEERING:
            return EvidenceResult(
                EvidenceStatus.ENGINEERING_COVERED, EvidencePolicy.ENGINEERING,
                self.catalog.semantic_revision,
                ("Required engineering quality is governed by ATHBA coding/engineering policy, "
                 "not independently proven by product behavioral acceptance.",),
            ).to_record(item)
        if decision.policy == EvidencePolicy.BEHAVIORAL:
            result = await self.behavioral.reconcile(ChecklistReconciliationRequest(
                request.project_id, item.ref, item.text, request.accepted))
            return result.to_dict()
        snapshot = GitSpecificationSnapshot(self.catalog.repository_root).read(self.catalog.semantic_revision)
        adapter = self.adapters.for_language(request.language_id)
        if adapter is None:
            status = EvidenceStatus.NOT_REQUIRED if decision.policy == EvidencePolicy.NON_GOAL else EvidenceStatus.UNSUPPORTED
            result_static = EvidenceResult(status, decision.policy,
                                           snapshot.revision, ("no language evidence adapter",))
        else:
            result_static = adapter.verify(decision, snapshot)
        record = result_static.to_record(item)
        record["inspected_paths"] = [file.path for file in snapshot.files]
        if adapter is not None:
            record["adapter"] = {"id": adapter.descriptor.adapter_id,
                                 "version": adapter.descriptor.adapter_version,
                                 "language": adapter.descriptor.language_id}
        return record


def required_source_subjects(checklist: SpecificationChecklist) -> tuple[str, ...]:
    subjects = []
    for item in checklist.items:
        quote = getattr(item, "source_quote", "") or item.text
        decision = EvidencePolicyRouter().route(item)
        if decision.modality == ObligationModality.REQUIRED and quote in checklist.requirement_text:
            subjects.append(decision.subject)
    return tuple(subjects)
