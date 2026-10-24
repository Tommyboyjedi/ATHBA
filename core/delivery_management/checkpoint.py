"""Deferred main synchronization only at the BDE's explicit quiescent checkpoint."""
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from core.delivery_management.authority_store import AuthorityStore
from core.delivery_management.branch_environment import BranchEnvironment
from core.delivery_management.dispatch import verify_scope
from core.delivery_management.domain import ManagementRequest, MergeKind, MergeRecord, MergeStatus
from core.delivery_management.merge_publication import MergeAuthority, authority_digest
from core.delivery_management.evidence import AcceptedContribution, CompletedEvidenceRequest
from core.delivery_management.merge_service import MergeManagement
from core.delivery_management.store import ManagementStore, RecordIdentity
from core.development.feature_management_checkpoint import FeatureCheckpointRequest, FeatureCheckpointResult


@dataclass(frozen=True)
class CheckpointDependencies:
    records: ManagementStore
    merges: MergeManagement
    load_authority: Callable[[CompletedEvidenceRequest], AcceptedContribution]


@dataclass(frozen=True)
class CheckpointBinding:
    identity: RecordIdentity
    worker_token: str
    environment: BranchEnvironment


@dataclass(frozen=True)
class ManagedCheckpoint:
    dependencies: CheckpointDependencies
    binding: CheckpointBinding

    def resume_available(self, request: FeatureCheckpointRequest) -> bool:
        try:
            return PublishedCheckpointReplay(self.dependencies, self.binding).recover(request) is not None
        except ValueError:
            return False

    async def synchronize(self, request: FeatureCheckpointRequest) -> FeatureCheckpointResult | None:
        deps, binding = self.dependencies, self.binding
        record = deps.records.delivery(binding.identity)
        if record is None:
            raise ValueError("checkpoint delivery authority is unavailable")
        if (request.project_id != record.project_id or record.worker_token != binding.worker_token
                or request.state.delivery_identity != record.id
                or request.state.source_requirement_hash != record.behavior.source_sha256
                or request.state.canonical_ref != record.branch_ref):
            raise ValueError("checkpoint belongs to another project/worker/source authority")
        replay = PublishedCheckpointReplay(deps, binding).recover(request)
        if replay is not None:
            return replay
        if not record.pending_sync:
            return None
        verify_scope(record)
        contribution = deps.load_authority(CompletedEvidenceRequest(
            Path(record.state_root), record.project_id, record.id, record.behavior.id,
            record.behavior.source_sha256, record.architecture_sha256, binding.environment))
        artifact = AuthorityStore(deps.records).save(contribution)
        deps.records.update_delivery((binding.identity, lambda value: replace(value,
            checkpoint_authority_file=artifact.path, checkpoint_authority_sha256=artifact.sha256)))
        operation = deps.merges.synchronize_checkpoint((ManagementRequest(
            record.project_id, record.id, "delivery-checkpoint:" + binding.worker_token), binding.worker_token))
        if operation.status != MergeStatus.PUBLISHED or operation.candidate_revision is None:
            return None
        return _checkpoint_result(deps.records, operation)


@dataclass(frozen=True)
class PublishedCheckpointReplay:
    """Reconnect a published synchronization receipt after a feature-save interruption."""
    dependencies: CheckpointDependencies
    binding: CheckpointBinding

    def recover(self, request: FeatureCheckpointRequest) -> FeatureCheckpointResult | None:
        deps, binding = self.dependencies, self.binding
        record = deps.records.delivery(binding.identity)
        if record is None:
            raise ValueError("checkpoint delivery authority is unavailable")
        if (request.project_id != record.project_id or record.worker_token != binding.worker_token
                or request.state.delivery_identity != record.id
                or request.state.source_requirement_hash != record.behavior.source_sha256
                or request.state.canonical_ref != record.branch_ref):
            raise ValueError("published checkpoint belongs to different worker/source authority")
        if request.state.canonical_development_base == record.trusted_revision:
            return None
        candidates = tuple(deps.records.merge(RecordIdentity(record.project_id, identity))
                           for identity in record.synchronization_records)
        matches = tuple(operation for operation in candidates if operation is not None
            and operation.kind == MergeKind.SYNCHRONIZATION and operation.status == MergeStatus.PUBLISHED
            and operation.project_id == record.project_id and operation.delivery_id == record.id
            and operation.delivery_revision == request.state.canonical_development_base
            and operation.candidate_revision == record.trusted_revision
            and operation.main_revision == record.synchronized_main)
        if len(matches) != 1:
            raise ValueError("feature baseline differs without one exact published synchronization receipt")
        operation = matches[0]
        context = MergeAuthority(deps.merges.dependencies).load(operation)
        approval = operation.approval
        if (not operation.publication_intent or approval is None or not approval.actor_reference
                or approval.operation_id != operation.id
                or approval.main_revision != operation.main_revision
                or approval.delivery_revision != operation.delivery_revision
                or approval.candidate_revision != operation.candidate_revision
                or approval.authority_digest != authority_digest(context)):
            raise ValueError("published synchronization receipt lacks exact validated approval authority")
        verify_scope(record)
        return _checkpoint_result(deps.records, operation)


def _checkpoint_result(records: ManagementStore, operation: MergeRecord) -> FeatureCheckpointResult:
    if operation.candidate_revision is None:
        raise ValueError("published synchronization has no candidate revision")
    return FeatureCheckpointResult(operation.candidate_revision, (
        str(records.path((RecordIdentity(operation.project_id, operation.id), "merges"))),
        *operation.evidence_refs))
