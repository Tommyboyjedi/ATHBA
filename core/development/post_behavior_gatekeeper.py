"""Reuse independent checklist reconciliation after exact accepted-test preservation."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from core.development.checklist_reconciliation_tree import (
    ChecklistReconciliationTree, ChecklistTreeContext, validate_persisted_tree,
)
from core.development.post_behavior_domain import PostBehaviorState, ValidationEvidence
from core.development.post_behavior_ports import ReconciliationCheckpoint
from core.development.post_behavior_entry import AcceptedBehavioralDelivery
from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
from core.development.post_behavior_validation import PostBehaviorCandidateAuthority
from core.development.reconciliation_progress import (
    ChecklistItemProgress, ReconciliationJournal, ReconciliationJournalRequest, evidence_digest,
)
from core.development.specification_domain import SpecificationGatekeeperRunState, SpecificationChecklistItem
from core.development.specification_evidence_policy import reconciliation_satisfied
from core.development.specification_evidence_routing import RoutedChecklistReconciler, required_source_subjects
from core.development.specification_reconciliation import ChecklistItemReconciler, GitAcceptedTestCatalog
from core.execution.reasoning_gateway import ReasoningGateway


@dataclass(frozen=True)
class PostBehaviorGatekeeperDependencies:
    delivery: AcceptedBehavioralDelivery
    authority: PostBehaviorCandidateAuthority
    evidence: PostBehaviorEvidenceStore
    reasoning: ReasoningGateway


class PostBehaviorGatekeeper:
    """Change only the mechanically verified evidence revision; reuse the existing evaluator."""

    def __init__(self, dependencies: PostBehaviorGatekeeperDependencies):
        self.dependencies = dependencies

    async def reconcile_candidate(self, state: PostBehaviorState, checkpoint: ReconciliationCheckpoint) -> ValidationEvidence:
        deps = self.dependencies
        deps.authority.verify_history(state)
        active = state.active_pass
        if active is None or active.candidate is None or active.candidate.revision is None:
            raise ValueError("Gatekeeper requires a persisted candidate")
        revision = active.candidate.revision
        baseline = state.behaviorally_accepted_revision
        root = Path(deps.delivery.project.repository_root)
        original = GitAcceptedTestCatalog(root, baseline)
        if any(original.verified_source(item) is None for item in deps.delivery.accepted_tests):
            raise ValueError("original accepted test evidence is not preserved at behavioral baseline")
        # The complete exact-rename/refactor chain was mechanically verified above.
        # Original semantic SHAs remain in the immutable delivery/evidence manifest.
        accepted = [replace(item, semantic_revision=revision) for item in deps.delivery.accepted_tests]
        catalog = GitAcceptedTestCatalog(root, revision)
        if any(catalog.verified_source(item) is None for item in accepted):
            raise ValueError("candidate omits an accepted test identity")
        keeper = SpecificationGatekeeperRunState.from_dict(dict(deps.delivery.feature.gatekeeper_payload or {}))
        identity = evidence_digest({"authority": state.entry.behavioral_authority_digest,
            "checklist": keeper.checklist.to_dict(),
            "accepted": [{"origin": original_item.to_dict(), "candidate": item.to_dict(),
                          "verified_source": catalog.verified_source(item)}
                         for original_item, item in zip(deps.delivery.accepted_tests, accepted)]})
        def persist(progress):
            checkpoint(tuple(ChecklistItemProgress.from_dict(item) for item in progress))
        journal = ReconciliationJournal(ReconciliationJournalRequest(
            revision, identity, tuple(item.to_dict() for item in active.reconciliation_progress),
            persist, tuple(keeper.checklist.item_refs())))
        roots = [SpecificationChecklistItem.from_dict(item.to_dict()) for item in keeper.checklist.items]
        validate_persisted_tree(journal, roots)
        tree = ChecklistReconciliationTree(journal, deps.reasoning)
        reconciler = RoutedChecklistReconciler(ChecklistItemReconciler(deps.reasoning, catalog), catalog)
        results = []
        for item in roots:
            context = ChecklistTreeContext(reconciler, keeper.checklist.project_id,
                keeper.checklist.requirement_text, accepted, deps.delivery.project.runtime.kind,
                required_source_subjects(keeper.checklist), revision, item)
            results.extend(await tree.reconcile(context))
        ref = deps.evidence.record("specification_reconciliation", {
            "revision": revision, "behavioral_baseline": baseline,
            "authority_digest": state.entry.behavioral_authority_digest, "results": results,
            "original_accepted_tests": [item.to_dict() for item in deps.delivery.accepted_tests]})
        return ValidationEvidence(revision, reconciliation_satisfied(tuple(results)), (ref,))
