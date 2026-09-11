"""Restartable recursive checklist evaluation using feature-owned checkpoints."""
from __future__ import annotations

from dataclasses import dataclass, replace

from core.development.checklist_split_progress import (
    ChecklistSplitAncestry, MAX_CHECKLIST_SPLIT_DEPTH, UNSPLITTABLE_REASON, split_structure,
)
from core.development.reconciliation_progress import (
    ChecklistItemProgress, ChecklistSplitProgress, IndividualEvidenceProgress,
    PendingReconciliationCall, ReconciliationJournal, incompatible,
)
from core.development.specification_atomization import ChecklistSplitRequest, SpecificationChecklistPlanner
from core.development.specification_domain import SpecificationChecklistItem
from core.development.specification_evidence_policy import EvidencePolicyRouter
from core.development.specification_evidence_routing import RoutedChecklistReconciler, RoutedChecklistRequest
from core.development.specification_obligations import EvidencePolicy
from core.development.specification_reconciliation import AcceptedTestEvidence
from core.execution.reasoning_gateway import ReasoningGateway


@dataclass(frozen=True)
class ChecklistTreeContext:
    reconciler: RoutedChecklistReconciler
    project_id: str
    source: str
    accepted: list[AcceptedTestEvidence]
    language: str
    required_subjects: tuple[str, ...]
    revision: str
    item: SpecificationChecklistItem
    ancestry: ChecklistSplitAncestry = ChecklistSplitAncestry()


class ChecklistNodeCheckpoint:
    """Translate local result boundaries into durable item upserts."""

    def __init__(self, journal: ReconciliationJournal, context: ChecklistTreeContext):
        self.journal = journal
        self.state = journal.restore(context.item, tuple(item.ref for item in context.ancestry.items))

    def save(self, state: ChecklistItemProgress) -> None:
        self.state = state
        self.journal.save(state)

    def before_test(self) -> None:
        self.save(replace(self.state, pending_call=PendingReconciliationCall.TEST))

    def attempts(self, attempts: tuple[IndividualEvidenceProgress, ...]) -> None:
        self.save(replace(self.state, individual_attempts=attempts, pending_call=PendingReconciliationCall.NONE))

    def result(self, record: dict[str, object]) -> None:
        self.save(replace(self.state, result=record))

    def before_split(self) -> None:
        self.save(replace(self.state, pending_call=PendingReconciliationCall.SPLIT))

    def split(self, split: ChecklistSplitProgress) -> None:
        record = dict(self.state.result or {})
        record.update({"parent_item": self.state.item.to_dict(), "trusted_revision": self.state.trusted_revision,
                       "ancestry": list(self.state.ancestry), "split_depth": len(self.state.ancestry),
                       "split_rationale": split.rationale, "attempted_split": split.attempted_response,
                       "rejection_reason": split.rejection_reason})
        if split.disposition == "unsplittable":
            record.update({"status": "unsplittable", "blocked_reason": UNSPLITTABLE_REASON})
        else:
            record.update({"status": "superseded", "child_refs": [child.ref for child in split.children]})
        self.save(replace(self.state, result=record, split=split, pending_call=PendingReconciliationCall.NONE))


class ChecklistReconciliationTree:
    """Evaluate unresolved nodes; persisted parents retain their exact children."""

    def __init__(self, journal: ReconciliationJournal, gateway: ReasoningGateway):
        self.journal = journal
        self.planner = SpecificationChecklistPlanner(gateway)

    async def reconcile(self, context: ChecklistTreeContext) -> list[dict[str, object]]:
        try:
            decision = EvidencePolicyRouter().route_source(context.item, context.source)
        except ValueError:
            # A cached YES cannot bypass revalidation of a persisted root/child.
            return [await context.reconciler.reconcile(RoutedChecklistRequest(
                context.project_id, context.item, context.source, context.accepted))]
        checkpoint = ChecklistNodeCheckpoint(self.journal, context)
        if checkpoint.state.result is None:
            record = await context.reconciler.reconcile(RoutedChecklistRequest(
                context.project_id, context.item, context.source, context.accepted, context.language,
                context.required_subjects, checkpoint.state.individual_attempts,
                checkpoint.attempts, checkpoint.before_test))
            checkpoint.result(record)
        record = dict(checkpoint.state.result or {})
        if (decision.policy != EvidencePolicy.BEHAVIORAL
                or record.get("answer") != "NO"):
            return [record]
        if checkpoint.state.split is None:
            await self._split(context, checkpoint)
        split = checkpoint.state.split
        if split is None:
            raise AssertionError("split checkpoint was not persisted")
        results = [dict(checkpoint.state.result or {})]
        if split.disposition == "unsplittable":
            return results
        ancestry = ChecklistSplitAncestry((*context.ancestry.items, context.item),
                                          (*context.ancestry.structures, split_structure(split.children)))
        for child in split.children:
            results.extend(await self.reconcile(replace(context, item=child, ancestry=ancestry)))
        return results

    async def _split(self, context: ChecklistTreeContext, checkpoint: ChecklistNodeCheckpoint) -> None:
        if len(context.ancestry.items) >= MAX_CHECKLIST_SPLIT_DEPTH:
            checkpoint.split(ChecklistSplitProgress("unsplittable", "Checklist split depth limit reached.",
                                                   rejection_reason="split_depth_exhausted"))
            return
        item = context.item
        checkpoint.before_split()
        split = await self.planner.split_item(ChecklistSplitRequest(
            context.project_id, context.source, item.ref, item.text, item.kind, item.modality,
            item.source_quote, item.subject,
            tuple(attempt.to_dict() for attempt in checkpoint.state.individual_attempts),
            context.revision, context.ancestry))
        occupied = {entry.item.ref for entry in self.journal.items} | set(self.journal.request.root_refs)
        if any(child.ref in occupied for child in split.children):
            checkpoint.split(ChecklistSplitProgress("unsplittable", split.rationale,
                attempted_response=split.attempted_response, rejection_reason="child_ref_collision"))
            return
        checkpoint.split(ChecklistSplitProgress(split.disposition, split.rationale, split.children,
                                               split.attempted_response, split.rejection_reason))


def validate_persisted_tree(journal: ReconciliationJournal, roots: list[SpecificationChecklistItem]) -> None:
    """Reject orphaned, altered, or colliding saved nodes before reasoning resumes."""
    expected: dict[str, tuple[SpecificationChecklistItem, tuple[str, ...]]] = {
        item.ref: (item, ()) for item in roots}
    if len(expected) != len(roots):
        raise incompatible("duplicate root checklist refs")
    for entry in journal.items:
        identity = expected.get(entry.item.ref)
        if identity != (entry.item, entry.ancestry):
            raise incompatible("persisted reconciliation tree identity changed")
        if entry.split is not None:
            for index, child in enumerate(entry.split.children, 1):
                if child.ref != f"{entry.item.ref}-S{index:03d}" or child.ref in expected:
                    raise incompatible("persisted split child identity changed")
                expected[child.ref] = (child, (*entry.ancestry, entry.item.ref))
