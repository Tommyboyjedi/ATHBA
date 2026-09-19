"""Bind this lane to durable completion evidence from the existing behavioral path."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.behavior_contract_domain import BehaviorContract
from core.development.post_behavior_domain import PostBehaviorEntry, ValidationEvidence
from core.development.post_behavior_git import PostBehaviorGit
from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService
from core.development.reconciliation_progress import evidence_digest
from core.development.specification_domain import SpecificationGatekeeperRunState
from core.development.specification_evidence_policy import reconciliation_satisfied
from core.development.specification_reconciliation import (
    AcceptedTestEvidence, CompletedMicrocycleEvidenceCollector, GitAcceptedTestCatalog,
)
from core.development.strict_tdd_feature_domain import StrictTddFeatureState, StrictTddFeatureStatus
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository


@dataclass(frozen=True)
class AcceptedBehavioralDelivery:
    entry: PostBehaviorEntry
    project: DevelopmentProject
    feature: StrictTddFeatureState
    contract: BehaviorContract
    accepted_tests: tuple[AcceptedTestEvidence, ...]


@dataclass(frozen=True)
class AcceptedBehavioralDeliveryLoader:
    state_root: Path

    def load(self, project_id: str) -> AcceptedBehavioralDelivery:
        feature = StrictTddFeatureRepository(self.state_root / "features").load(project_id)
        project = ProjectEnvironmentService(self.state_root / "projects").repo.load(project_id)
        if feature is None or project is None:
            raise ValueError("existing behavioral feature and project state required")
        if feature.status != StrictTddFeatureStatus.COMPLETED.value:
            raise ValueError("post-behavior requires completed behavioral delivery")
        if not reconciliation_satisfied(feature.final_reconciliation):
            raise ValueError("post-behavior requires final Specification Gatekeeper acceptance")
        if not feature.behavioral_entry_revision or not feature.canonical_development_base:
            raise ValueError("behavioral entry revision was not durably recorded")
        if feature.current_scenario_id or feature.working_revision or feature.pending_completed_behavior:
            raise ValueError("behavioral execution is still active")
        contract = BehaviorContract.from_dict(dict(feature.contract_payload or {}))
        checklist = SpecificationGatekeeperRunState.from_dict(dict(feature.gatekeeper_payload or {}))
        recorded = {str(item.get("checklist_ref")) for item in feature.final_reconciliation}
        if not set(checklist.checklist.item_refs()).issubset(recorded):
            raise ValueError("final Gatekeeper evidence omits checklist authority")
        if {item.behavior_ref for item in feature.completed_behaviors} != set(contract.requirement_refs()):
            raise ValueError("behavioral delivery has incomplete accepted requirements")
        store = MicrocycleStateRepo(self.state_root / "microcycles")
        states = [store.load(item.scenario_id) for item in feature.completed_behaviors]
        if any(item is None for item in states):
            raise ValueError("completed microcycle evidence is unavailable")
        accepted = CompletedMicrocycleEvidenceCollector().collect(tuple(item for item in states if item is not None))
        catalog = GitAcceptedTestCatalog(Path(project.repository_root), feature.canonical_development_base)
        if len(accepted) != len(states) or any(catalog.verified_source(item) is None for item in accepted):
            raise ValueError("behavioral baseline does not preserve every accepted test")
        git = PostBehaviorGit(Path(project.repository_root))
        git.snapshot(feature.behavioral_entry_revision)
        git.snapshot(feature.canonical_development_base)
        digest = evidence_digest({"contract": contract.to_dict(), "gatekeeper": feature.gatekeeper_payload,
                                  "results": feature.final_reconciliation,
                                  "tests": [item.to_dict() for item in accepted]})
        entry = PostBehaviorEntry(project_id, feature.behavioral_entry_revision,
            feature.canonical_development_base, tuple(contract.production_paths), digest,
            ValidationEvidence(feature.canonical_development_base, True, (f"behavioral-authority:{digest}",)))
        return AcceptedBehavioralDelivery(entry, project, feature, contract, tuple(accepted))
