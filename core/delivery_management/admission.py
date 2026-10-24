"""Admit approved behavior branches without making display order a dependency."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.development.project_environment import ProjectEnvironmentService
from core.delivery_management.domain import DeliveryPhase, TeamDelivery, delivery_identity
from core.delivery_management.git_workspaces import BranchWorkspace, GitWorkspaces
from core.delivery_management.store import ManagementStore, RecordIdentity
from core.project_setup.architecture import PinnedArchitectureApproval, content_hash
from core.project_setup.delivery import DeliveryRequest
from core.project_setup.records import ProjectSetupRepository, SetupStatus
from core.project_setup.service import ExistingProjects


@dataclass(frozen=True)
class AdmissionDependencies:
    projects: ExistingProjects
    approvals: PinnedArchitectureApproval
    setups: ProjectSetupRepository
    parent: ProjectEnvironmentService
    store: ManagementStore


class BranchAdmission:
    def __init__(self, dependencies: AdmissionDependencies):
        self.dependencies = dependencies

    async def prepare(self, request: DeliveryRequest) -> TeamDelivery:
        deps = self.dependencies
        handoff, decision = request.handoff, request.handoff.decision
        deps.approvals.require(handoff)
        parent_project = await deps.projects.get_project_by_id(decision.project_id)
        specification = await deps.projects.get_latest_spec(decision.project_id)
        if parent_project is None or str(parent_project.id) != decision.project_id:
            raise ValueError("behavior delivery requires its existing frontend project")
        if (specification is None or specification.get("version") != decision.specification_version
                or content_hash(specification.get("content")) != decision.specification_sha256):
            raise ValueError("approved project specification identity differs")
        behavior = next((item for item in decision.behaviors if item.id == request.behavior_id), None)
        if behavior is None:
            raise ValueError("unknown approved full behavior")
        setup = deps.setups.load(decision.project_id)
        if (setup is None or setup.status != SetupStatus.READY or not setup.environment_verified
                or setup.architecture_sha256 != decision.digest or not setup.bde_language_compatible):
            raise ValueError("approved compatible application environment is not ready")
        if setup.deliveries or setup.active_delivery:
            raise ValueError("legacy shared-checkout delivery state requires explicit compatibility review")
        identity = delivery_identity((decision.project_id, behavior.id, decision.digest))
        key = RecordIdentity(decision.project_id, identity)
        with deps.store.locked((decision.project_id, "prepare-" + identity)):
            existing = deps.store.delivery(key)
            if existing is not None:
                if existing.behavior != behavior or existing.architecture_sha256 != decision.digest:
                    raise ValueError("existing delivery source or architecture identity differs")
                return existing
            with deps.store.locked((decision.project_id, "integration")):
                parent = deps.parent.repo.load(decision.project_id)
                if parent is None:
                    raise ValueError("prepared parent environment is unavailable")
                root = Path(parent.repository_root)
                actual = GitWorkspaces().revision(root, "refs/heads/" + parent.default_ref)
                if actual != parent.trusted_base_sha:
                    raise ValueError("application main publication requires reconciliation")
                catalog = deps.store.catalog(decision.project_id)
                if not catalog:
                    if actual != setup.scaffold_revision:
                        raise ValueError("existing main lacks application integration provenance")
                    deps.store.save_catalog((decision.project_id, {
                        "revision": actual, "authority_files": [], "authority_hashes": {},
                        "integrated_deliveries": []}))
                elif catalog["revision"] != actual:
                    raise ValueError("application main evidence catalog is not current")
                ready = {item.behavior.id for item in deps.store.deliveries(decision.project_id)
                         if item.id in catalog["integrated_deliveries"]}
                if not set(behavior.depends_on) <= ready:
                    raise ValueError("behavior dependency is not integrated into application main")
                owned = deps.store.directory(decision.project_id) / "worktrees"
                target = owned / identity
                branch = "refs/heads/athba/deliveries/" + identity
                GitWorkspaces().prepare(BranchWorkspace(
                    root, target, branch, actual, owned, "refs/heads/" + parent.default_ref))
                record = TeamDelivery(identity, decision.project_id, behavior, decision.digest,
                    decision.specification_version, decision.specification_sha256, decision.version,
                    branch, str(target), str(deps.store.directory(decision.project_id) / "state" / identity),
                    actual, actual, actual, scope_base_revision=actual)
                deps.store.save_delivery(record)
                return record
