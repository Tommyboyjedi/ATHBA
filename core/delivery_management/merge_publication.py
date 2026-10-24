"""Management publication journals for exact validated branch/main merge candidates."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService
from core.delivery_management.domain import (
    DeliveryPhase, ManagementApproval, MergeKind, MergeRecord, MergeStatus, TeamDelivery,
)
from core.delivery_management.evidence import AcceptedContribution
from core.delivery_management.git_workspaces import require_owned
from core.delivery_management.publication import CheckedPublication, PromotionRequest
from core.delivery_management.store import ManagementStore, RecordIdentity
from core.delivery_management.validation import IntegrationValidator


@dataclass(frozen=True)
class MergeDependencies:
    store: ManagementStore
    parentenv: ProjectEnvironmentService
    validator: IntegrationValidator


@dataclass(frozen=True)
class MergeAuthorityContext:
    operation: MergeRecord
    delivery: TeamDelivery
    parent: DevelopmentProject
    contributions: tuple[AcceptedContribution, ...]
    authority_hashes: dict[str, str]


def authority_snapshot(dependencies: MergeDependencies, operation: MergeRecord) -> Path:
    return dependencies.store.directory(operation.project_id) / "validation" / f"{operation.id}-authority.json"


def authority_digest(context: MergeAuthorityContext) -> str:
    payload = {
        "main": context.operation.main_revision, "delivery": context.operation.delivery_revision,
        "candidate": context.operation.candidate_revision, "files": context.authority_hashes,
        "validation": {ref: sha256(Path(ref).read_bytes()).hexdigest() for ref in context.operation.evidence_refs
                       if Path(ref).is_absolute()},
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_completed_authority(context: MergeAuthorityContext) -> None:
    if context.operation.kind != MergeKind.INTEGRATION:
        return
    delivery = context.delivery
    selected = [value for value in context.contributions if value.delivery_id == delivery.id]
    if delivery.phase != DeliveryPhase.COMPLETE or len(selected) != 1:
        raise ValueError("integration no longer identifies a completed delivery")
    contribution = selected[0]
    if (contribution.completion_revision, contribution.source_sha256, contribution.architecture_sha256,
        contribution.behavior_id) != (delivery.completion_revision, delivery.behavior.source_sha256,
                                      delivery.architecture_sha256, delivery.behavior.id):
        raise ValueError("delivery source/completion/architecture authority changed")
    if delivery.authority_file not in context.authority_hashes:
        raise ValueError("delivery completed-evidence identity changed")
    if context.authority_hashes[delivery.authority_file] != delivery.authority_sha256:
        raise ValueError("delivery completed-evidence hash changed")


class MergeAuthority:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def load(self, operation: MergeRecord) -> MergeAuthorityContext:
        deps = self.dependencies
        identity = RecordIdentity(operation.project_id, operation.delivery_id)
        delivery = deps.store.delivery(identity)
        parent = deps.parentenv.repo.load(operation.project_id)
        if delivery is None or parent is None:
            raise ValueError("merge requires existing parent and delivery authority")
        snapshot = authority_snapshot(deps, operation)
        if not snapshot.is_file():
            raise ValueError("merge has no pinned accepted-evidence authority snapshot")
        hashes = read_json_file(snapshot)["files"]
        contributions = tuple(self._contribution((operation.project_id, path, digest))
                              for path, digest in hashes.items())
        if tuple(hashes) != operation.authority_files:
            raise ValueError("merge authority references differ from their pinned snapshot")
        return MergeAuthorityContext(operation, delivery, parent, contributions, hashes)

    def pin(self, operation: MergeRecord, files: dict[str, str]) -> MergeRecord:
        snapshot = authority_snapshot(self.dependencies, operation)
        files = dict(sorted(files.items()))
        if snapshot.exists():
            if read_json_file(snapshot) != {"files": files}:
                raise ValueError("merge evidence authority changed after preparation")
        else:
            write_json_atomically(snapshot, {"files": files})
        for path, digest in files.items():
            self._contribution((operation.project_id, path, digest))
        return replace(operation, authority_files=tuple(files), evidence_refs=(str(snapshot),))

    def _contribution(self, request: tuple[str, str, str]) -> AcceptedContribution:
        project_id, filename, expected = request
        path = require_owned(Path(filename), self.dependencies.store.directory(project_id))
        if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("accepted-evidence authority changed")
        contribution = AcceptedContribution.from_dict(read_json_file(path))
        if contribution.project_id != project_id:
            raise ValueError("accepted-evidence contribution belongs to another project")
        return contribution


@dataclass(frozen=True)
class PublicationInput:
    context: MergeAuthorityContext
    approval: ManagementApproval


class MergePublication:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def publish(self, request: PublicationInput) -> MergeRecord:
        context, approval = request.context, request.approval
        operation = context.operation
        self._approval(request)
        intent = replace(operation, publication_intent=True)
        self.dependencies.store.save_merge(intent)
        promotion = self._promotion(context)
        CheckedPublication().promote(promotion)
        return self._finish(replace(context, operation=intent))

    def recover(self, context: MergeAuthorityContext) -> MergeRecord:
        if not context.operation.publication_intent or context.operation.approval is None:
            raise ValueError("merge publication has no durable exact approval/intent")
        self._approval(PublicationInput(context, context.operation.approval))
        CheckedPublication().recover(self._promotion(context))
        return self._finish(context)

    def _approval(self, request: PublicationInput) -> None:
        context, approval = request.context, request.approval
        operation = context.operation
        verify_completed_authority(context)
        if operation.status not in {MergeStatus.APPROVED, MergeStatus.PUBLISHED}:
            raise ValueError("merge candidate is not approved")
        if approval != operation.approval or approval.operation_id != operation.id:
            raise ValueError("management approval does not identify this exact candidate")
        if (approval.main_revision, approval.delivery_revision, approval.candidate_revision,
            approval.authority_digest) != (operation.main_revision, operation.delivery_revision,
                                           operation.candidate_revision, authority_digest(context)):
            raise ValueError("management approval pins different revision/evidence authority")
        if not approval.actor_reference:
            raise ValueError("management approval requires an attributed actor")

    def _promotion(self, context: MergeAuthorityContext) -> PromotionRequest:
        operation, parent, delivery = context.operation, context.parent, context.delivery
        if operation.candidate_revision is None:
            raise ValueError("merge candidate revision is missing")
        target = Path(parent.repository_root) if operation.kind == MergeKind.INTEGRATION else Path(delivery.worktree)
        ref = "refs/heads/" + parent.default_ref if operation.kind == MergeKind.INTEGRATION else delivery.branch_ref
        expected = operation.main_revision if operation.kind == MergeKind.INTEGRATION else operation.delivery_revision
        return PromotionRequest(Path(parent.repository_root), target, ref, expected, operation.candidate_revision)

    def _finish(self, context: MergeAuthorityContext) -> MergeRecord:
        operation = context.operation
        if operation.candidate_revision is None:
            raise ValueError("publication candidate is missing")
        if operation.kind == MergeKind.INTEGRATION:
            IntegratedMetadata(self.dependencies).record(context)
        else:
            SynchronizedMetadata(self.dependencies).record(context)
        result = replace(operation, status=MergeStatus.PUBLISHED)
        self.dependencies.store.save_merge(result)
        return result


class IntegratedMetadata:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def record(self, context: MergeAuthorityContext) -> None:
        deps, operation = self.dependencies, context.operation
        parent = deps.parentenv.repo.load(operation.project_id)
        candidate = operation.candidate_revision
        if parent is None or candidate is None:
            raise ValueError("published application authority is unavailable")
        if parent.trusted_base_sha not in {operation.main_revision, candidate}:
            raise ValueError("publication recovery refuses newer application metadata")
        catalog = deps.store.catalog(operation.project_id)
        if catalog.get("revision", operation.main_revision) not in {operation.main_revision, candidate}:
            raise ValueError("publication recovery refuses newer accepted evidence catalog")
        if parent.trusted_base_sha != candidate:
            deps.parentenv.repo.save(replace(parent, trusted_base_sha=candidate))
        integrated = tuple(dict.fromkeys((*catalog.get("integrated_deliveries", ()), operation.delivery_id)))
        deps.store.save_catalog((operation.project_id, {
            "revision": candidate, "authority_files": list(operation.authority_files),
            "authority_hashes": context.authority_hashes, "integrated_deliveries": list(integrated),
        }))
        identity = RecordIdentity(operation.project_id, operation.delivery_id)
        def update(delivery: TeamDelivery) -> TeamDelivery:
            return replace(delivery, integration_records=tuple(dict.fromkeys((*delivery.integration_records, operation.id))))
        deps.store.update_delivery((identity, update))


class SynchronizedMetadata:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def record(self, context: MergeAuthorityContext) -> None:
        operation, deps = context.operation, self.dependencies
        candidate = operation.candidate_revision
        identity = RecordIdentity(operation.project_id, operation.delivery_id)
        def update(delivery: TeamDelivery) -> TeamDelivery:
            if candidate is None or delivery.trusted_revision not in {operation.delivery_revision, candidate}:
                raise ValueError("synchronization recovery refuses newer delivery metadata")
            return replace(delivery, trusted_revision=candidate, synchronized_main=operation.main_revision,
                pending_sync=delivery.pending_sync and delivery.pending_sync_revision != operation.main_revision,
                pending_sync_revision=None if delivery.pending_sync_revision == operation.main_revision else delivery.pending_sync_revision,
                scope_base_revision=candidate, synchronization_records=tuple(dict.fromkeys((*delivery.synchronization_records, operation.id))))
        deps.store.update_delivery((identity, update))
