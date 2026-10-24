"""Management-owned main synchronization and accepted contribution integration."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from core.atomic_json_file import write_json_atomically
from core.delivery_management.domain import (
    DeliveryPhase, ManagementApproval, ManagementRequest, MergeKind, MergeRecord, MergeStatus, TeamDelivery,
)
from core.delivery_management.git_merge import GitMerge, MergeCandidate, MergeRequest, merge_authority, merge_marker
from core.delivery_management.git_workspaces import GitCommand, GitWorkspaces, git, require_commit
from core.delivery_management.merge_publication import (
    MergeAuthority, MergeAuthorityContext, MergeDependencies, MergePublication, PublicationInput,
    authority_digest, verify_completed_authority,
)
from core.delivery_management.store import RecordIdentity
from core.delivery_management.validation import IntegrationValidationRequest


PUBLIC_SYNCHRONIZATION_PHASES = frozenset({DeliveryPhase.READY, DeliveryPhase.COMPLETE})


def required_delivery(dependencies: MergeDependencies, identity: RecordIdentity) -> TeamDelivery:
    value = dependencies.store.delivery(identity)
    if value is None:
        raise ValueError("unknown behavior delivery")
    return value


def within_scope(path: str, scopes: tuple[str, ...]) -> bool:
    return any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in scopes)


def verify_delivery_scope(delivery: TeamDelivery) -> None:
    baseline = delivery.scope_base_revision or delivery.fork_revision
    root = Path(delivery.worktree)
    git(GitCommand(root, ("merge-base", "--is-ancestor", baseline, delivery.trusted_revision)))
    paths = git(GitCommand(root, ("diff", "--name-only", "-z", baseline, delivery.trusted_revision))).split("\0")
    permitted = delivery.behavior.production_paths + delivery.behavior.test_paths
    if any(path and not within_scope(path, permitted) for path in paths):
        raise ValueError("delivery contains changes outside its authorized current scope")


def clear_pending_sync(dependencies: MergeDependencies, operation: MergeRecord) -> None:
    if operation.kind == MergeKind.SYNCHRONIZATION:
        identity = RecordIdentity(operation.project_id, operation.delivery_id)
        dependencies.store.update_delivery((identity, lambda value: replace(
            value, pending_sync=False, pending_sync_revision=None)
            if value.pending_sync_revision == operation.main_revision else value))


def pending_sync_update(dependencies: MergeDependencies, request: tuple[TeamDelivery, bool]) -> TeamDelivery:
    delivery, active_only = request
    if active_only and delivery.phase in PUBLIC_SYNCHRONIZATION_PHASES:
        return delivery
    parent = dependencies.parentenv.repo.load(delivery.project_id)
    if parent is None:
        raise ValueError("pending synchronization lost its parent environment")
    return replace(delivery, pending_sync=True, pending_sync_revision=parent.trusted_base_sha)


def unchanged_sync(dependencies: MergeDependencies, request: ManagementRequest) -> MergeRecord | None:
    delivery = required_delivery(dependencies, RecordIdentity(request.project_id, request.delivery_id))
    parent = dependencies.parentenv.repo.load(request.project_id)
    if parent is None or parent.trusted_base_sha != delivery.synchronized_main:
        return None
    root, workspace = Path(parent.repository_root), Path(delivery.worktree)
    GitWorkspaces().require_clean(root)
    GitWorkspaces().require_clean(workspace)
    if git(GitCommand(root, ("rev-parse", "refs/heads/" + parent.default_ref))) != parent.trusted_base_sha:
        raise ValueError("application ref differs from unchanged synchronization authority")
    if git(GitCommand(root, ("rev-parse", delivery.branch_ref))) != delivery.trusted_revision:
        raise ValueError("delivery ref differs from unchanged synchronization authority")
    verify_delivery_scope(delivery)
    operation = MergeRecord(uuid4().hex, request.project_id, request.delivery_id, MergeKind.SYNCHRONIZATION,
        parent.trusted_base_sha, delivery.trusted_revision, status=MergeStatus.NO_CHANGE,
        reason="delivery already includes this accepted main baseline; no candidate or validation fabricated")
    dependencies.store.save_merge(operation)
    clear_pending_sync(dependencies, operation)
    return operation


def verify_resolution_scope(context: MergeAuthorityContext, revision: str) -> None:
    root = Path(context.parent.repository_root)
    require_commit(root, revision)
    operation = context.operation
    base = operation.main_revision if operation.kind == MergeKind.INTEGRATION else operation.delivery_revision
    incoming = operation.delivery_revision if operation.kind == MergeKind.INTEGRATION else operation.main_revision
    common = git(GitCommand(root, ("merge-base", base, incoming)))
    inherited = set()
    for parent in (base, incoming):
        inherited.update(git(GitCommand(root, ("diff", "--name-only", "-z", common, parent))).split("\0"))
    tests = {node.test_path for contribution in context.contributions for node in contribution.tests}
    production = tuple(dict.fromkeys((*context.delivery.behavior.production_paths,
        *(node.production_path for contribution in context.contributions for node in contribution.tests))))
    changed = git(GitCommand(root, ("diff", "--name-only", "-z", base, revision))).split("\0")
    for path in changed:
        if path and path not in inherited and path not in tests and not within_scope(path, production):
            raise ValueError("supplied resolution changes an unattributed path outside accepted scope: " + path)


class MergePreparation:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def pin(self, request: tuple[ManagementRequest, MergeKind]) -> MergeRecord:
        management, kind = request
        deps = self.dependencies
        delivery = required_delivery(deps, RecordIdentity(management.project_id, management.delivery_id))
        parent = deps.parentenv.repo.load(management.project_id)
        if parent is None or not management.actor_reference:
            raise ValueError("merge requires existing parent authority and an attributed actor")
        if kind == MergeKind.INTEGRATION and delivery.phase != DeliveryPhase.COMPLETE:
            raise ValueError("integration requires an actually completed delivery")
        GitWorkspaces().require_clean(Path(parent.repository_root))
        GitWorkspaces().require_clean(Path(delivery.worktree))
        if git(GitCommand(Path(parent.repository_root), ("rev-parse", "refs/heads/" + parent.default_ref))) != parent.trusted_base_sha:
            raise ValueError("application main differs from its persisted trusted authority")
        if git(GitCommand(Path(delivery.worktree), ("rev-parse", delivery.branch_ref))) != delivery.trusted_revision:
            raise ValueError("delivery branch differs from its trusted authority")
        verify_delivery_scope(delivery)
        operation = MergeRecord(uuid4().hex, management.project_id, management.delivery_id,
                                kind, parent.trusted_base_sha, delivery.trusted_revision)
        files = self._files((operation, delivery))
        operation = MergeAuthority(deps).pin(operation, files)
        deps.store.save_merge(operation)
        return operation

    def _files(self, request: tuple[MergeRecord, TeamDelivery]) -> dict[str, str]:
        operation, delivery = request
        catalog = self.dependencies.store.catalog(operation.project_id)
        if catalog.get("revision", operation.main_revision) != operation.main_revision:
            raise ValueError("accepted-main evidence catalog is stale")
        hashes = catalog.get("authority_hashes", {})
        files = {path: hashes[path] for path in catalog.get("authority_files", ())}
        if delivery.phase == DeliveryPhase.COMPLETE:
            path, digest = delivery.authority_file, delivery.authority_sha256
        else:
            path, digest = delivery.checkpoint_authority_file, delivery.checkpoint_authority_sha256
        if path is None or digest is None:
            if operation.kind == MergeKind.INTEGRATION or delivery.trusted_revision != delivery.fork_revision:
                raise ValueError("synchronization needs actual accepted checkpoint evidence")
        else:
            if path in files and files[path] != digest:
                raise ValueError("accepted evidence identity ownership conflicts")
            files[path] = digest
        return files


class CandidateEvaluation:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def evaluate(self, operation: MergeRecord, resolution: str | None = None) -> MergeRecord:
        deps = self.dependencies
        context = MergeAuthority(deps).load(operation)
        trials = deps.store.directory(operation.project_id) / "trials"
        integration = operation.kind == MergeKind.INTEGRATION
        request = MergeRequest(Path(context.parent.repository_root), trials / operation.id,
            operation.main_revision if integration else operation.delivery_revision,
            operation.delivery_revision if integration else operation.main_revision,
            operation.id, trials)
        if resolution is not None:
            identity = operation.id + "-resolution-" + uuid4().hex
            request = replace(request, identity=identity, trial_root=trials / identity)
        try:
            self._completed(context)
            if resolution is None:
                candidate = GitMerge().prepare(request)
            else:
                verify_resolution_scope(context, resolution)
                candidate = ResolvedCandidate(self.dependencies).prepare((request, resolution))
            if candidate.conflicts:
                result = replace(operation, status=MergeStatus.CONFLICT, conflicts=candidate.conflicts,
                    reason="ordinary merge conflicts; neither live branch was changed")
            else:
                assert candidate.revision is not None
                self._protected((context, candidate.revision))
                validation = deps.validator.validate(IntegrationValidationRequest(
                    candidate.trial_root, candidate.revision, context.parent.runtime, context.contributions))
                evidence = deps.store.directory(operation.project_id) / "validation" / f"{operation.id}-{uuid4().hex}.json"
                write_json_atomically(evidence, validation.to_dict())
                result = replace(operation,
                    status=MergeStatus.VALIDATED if validation.passed else MergeStatus.FAILED,
                    candidate_revision=candidate.revision,
                    evidence_refs=(*operation.evidence_refs, str(evidence), *validation.evidence_refs),
                    reason=None if validation.passed else validation.diagnostic)
        except Exception as error:
            result = replace(operation, status=MergeStatus.FAILED,
                             reason=f"{type(error).__name__}: {error}")
        result = self._cleanup((request, result))
        deps.store.save_merge(result)
        if result.status in {MergeStatus.FAILED, MergeStatus.CONFLICT, MergeStatus.STALE}:
            clear_pending_sync(deps, result)
        return result

    def _cleanup(self, request: tuple[MergeRequest, MergeRecord]) -> MergeRecord:
        merge, result = request
        if not merge_marker(merge).exists():
            return result
        try:
            GitMerge().cleanup(merge)
            return result
        except Exception as error:
            return replace(result, status=MergeStatus.FAILED,
                reason=f"{result.reason or ''}; disposable merge cleanup uncertain: {type(error).__name__}: {error}")

    def _completed(self, context: MergeAuthorityContext) -> None:
        selected = [item for item in context.contributions if item.delivery_id == context.delivery.id]
        if context.operation.kind == MergeKind.INTEGRATION:
            if len(selected) != 1 or selected[0].kind != "completed":
                raise ValueError("integration requires retained completed BDE evidence")
            if selected[0].completion_revision != context.delivery.completion_revision:
                raise ValueError("completed BDE revision differs from its retained authority")
            if context.delivery.naming is None or context.delivery.refactoring is None:
                raise ValueError("integration requires recorded Naming and Refactoring outcomes")

    def _protected(self, request: tuple[MergeAuthorityContext, str]) -> None:
        context, revision = request
        base = context.operation.main_revision if context.operation.kind == MergeKind.INTEGRATION else context.operation.delivery_revision
        tests = {node.test_path for contribution in context.contributions for node in contribution.tests}
        production = tuple(dict.fromkeys((*context.delivery.behavior.production_paths,
            *(node.production_path for contribution in context.contributions for node in contribution.tests))))
        root = Path(context.parent.repository_root)
        paths = git(GitCommand(root, ("diff", "--name-only", "-z", base, revision))).split("\0")
        for path in paths:
            if not path or within_scope(path, production) or path in tests:
                continue
            old = git(GitCommand(root, ("ls-tree", base, "--", path)))
            if not old:
                continue
            new = git(GitCommand(root, ("ls-tree", revision, "--", path)))
            if not new:
                raise ValueError("merge removes unowned accepted baseline content: " + path)
            if old != new:
                raise ValueError("merge changes baseline content without accepted test authority: " + path)


class MergeApprovals:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def approve(self, identity: RecordIdentity, actor_reference: str) -> ManagementApproval:
        operation = self.dependencies.store.merge(identity)
        if operation is None or operation.status != MergeStatus.VALIDATED or operation.candidate_revision is None:
            raise ValueError("only an exact validated merge candidate can be approved")
        context = MergeAuthority(self.dependencies).load(operation)
        self.current(context)
        if not actor_reference:
            raise ValueError("management approval requires an attributed actor")
        approval = ManagementApproval(operation.id, actor_reference, operation.main_revision,
            operation.delivery_revision, operation.candidate_revision, authority_digest(context))
        self.dependencies.store.save_merge(replace(operation, status=MergeStatus.APPROVED, approval=approval))
        return approval

    def current(self, context: MergeAuthorityContext) -> None:
        operation, delivery, parent = context.operation, context.delivery, context.parent
        root = Path(parent.repository_root)
        actual = git(GitCommand(root, ("rev-parse", "refs/heads/" + parent.default_ref)))
        if actual != operation.main_revision or parent.trusted_base_sha != operation.main_revision:
            raise ValueError("stale merge candidate: application main advanced")
        actual_delivery = git(GitCommand(root, ("rev-parse", delivery.branch_ref)))
        if actual_delivery != operation.delivery_revision or delivery.trusted_revision != operation.delivery_revision:
            raise ValueError("stale merge candidate: delivery authority advanced")
        catalog = self.dependencies.store.catalog(operation.project_id)
        if catalog.get("revision", operation.main_revision) != operation.main_revision:
            raise ValueError("stale merge candidate: accepted-main evidence authority advanced")
        verify_completed_authority(context)
        current_files = catalog.get("authority_hashes", {})
        for path in catalog.get("authority_files", ()):
            if context.authority_hashes.get(path) != current_files[path]:
                raise ValueError("accepted-main evidence authority changed")


class MergeManagement:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def prepare(self, request: ManagementRequest, kind: MergeKind) -> MergeRecord:
        deps = self.dependencies
        delivery = required_delivery(deps, RecordIdentity(request.project_id, request.delivery_id))
        if kind == MergeKind.SYNCHRONIZATION and delivery.phase not in PUBLIC_SYNCHRONIZATION_PHASES:
            return self._deferred(request)
        with deps.store.locked((request.project_id, "worker-" + request.delivery_id)):
            current = required_delivery(deps, RecordIdentity(request.project_id, request.delivery_id))
            if kind == MergeKind.SYNCHRONIZATION and current.phase not in PUBLIC_SYNCHRONIZATION_PHASES:
                return self._deferred(request)
            return self._prepare((request, kind))

    def request_sync(self, request: ManagementRequest) -> MergeRecord:
        return self.prepare(request, MergeKind.SYNCHRONIZATION)

    def synchronize_checkpoint(self, request: tuple[ManagementRequest, str]) -> MergeRecord:
        management, token = request
        delivery = required_delivery(self.dependencies, RecordIdentity(management.project_id, management.delivery_id))
        if delivery.phase != DeliveryPhase.RUNNING or delivery.worker_token != token:
            raise ValueError("synchronization checkpoint is not owned by this worker")
        return self._prepare((management, MergeKind.SYNCHRONIZATION))

    def approve(self, identity: RecordIdentity, actor_reference: str) -> ManagementApproval:
        with self.dependencies.store.locked((identity.project_id, "integration")):
            return MergeApprovals(self.dependencies).approve(identity, actor_reference)

    def promote(self, identity: RecordIdentity, approval: ManagementApproval) -> MergeRecord:
        deps = self.dependencies
        with deps.store.locked((identity.project_id, "integration")):
            operation = deps.store.merge(identity)
            if operation is None:
                raise ValueError("unknown merge operation")
            with deps.store.locked((identity.project_id, "worker-" + operation.delivery_id)):
                if operation.status == MergeStatus.PUBLISHED:
                    return operation
                context = MergeAuthority(deps).load(operation)
                if operation.publication_intent:
                    return MergePublication(deps).recover(context, self._recovery_authority)
                try:
                    MergeApprovals(deps).current(context)
                except ValueError as error:
                    stale = replace(operation, status=MergeStatus.STALE, reason=str(error))
                    deps.store.save_merge(stale)
                    return stale
                return MergePublication(deps).publish(PublicationInput(context, approval))

    def recover(self, identity: RecordIdentity) -> MergeRecord:
        deps = self.dependencies
        with deps.store.locked((identity.project_id, "integration")):
            operation = deps.store.merge(identity)
            if operation is None:
                raise ValueError("unknown merge publication")
            with deps.store.locked((identity.project_id, "worker-" + operation.delivery_id)):
                if operation.status == MergeStatus.PUBLISHED:
                    return operation
                return MergePublication(deps).recover(
                    MergeAuthority(deps).load(operation), self._recovery_authority)

    def _recovery_authority(self, context: MergeAuthorityContext) -> None:
        if (context.operation.kind == MergeKind.SYNCHRONIZATION
                and context.delivery.phase not in PUBLIC_SYNCHRONIZATION_PHASES):
            raise ValueError("publication recovery requires a publicly quiescent delivery")
        MergeApprovals(self.dependencies).current(context)

    def validate_resolution(self, identity: RecordIdentity, revision: str) -> MergeRecord:
        return ResolutionManagement(self.dependencies).validate(identity, revision)

    def _prepare(self, request: tuple[ManagementRequest, MergeKind]) -> MergeRecord:
        return MergePreparationFlow(self.dependencies).prepare(request)

    def _deferred(self, request: ManagementRequest) -> MergeRecord:
        deps = self.dependencies
        parent = deps.parentenv.repo.load(request.project_id)
        if parent is None:
            raise ValueError("unknown application environment")
        identity = RecordIdentity(request.project_id, request.delivery_id)
        delivery = deps.store.update_delivery((identity,
            lambda value: pending_sync_update(deps, (value, True))))
        if delivery.phase in PUBLIC_SYNCHRONIZATION_PHASES:
            return self.prepare(request, MergeKind.SYNCHRONIZATION)
        operation = MergeRecord(uuid4().hex, request.project_id, request.delivery_id, MergeKind.SYNCHRONIZATION,
            delivery.pending_sync_revision or parent.trusted_base_sha, delivery.trusted_revision, status=MergeStatus.DEFERRED,
            reason="delivery is not publicly quiescent; synchronization waits for an owned accepted-REQ checkpoint")
        deps.store.save_merge(operation)
        return operation


class ResolvedCandidate:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def prepare(self, request: tuple[MergeRequest, str]) -> MergeCandidate:
        merge, revision = request
        root = merge.canonical_root
        for parent in (merge.base_revision, merge.incoming_revision):
            git(GitCommand(root, ("merge-base", "--is-ancestor", parent, revision)))
        actual = git(GitCommand(root, ("rev-parse", "--verify", f"{revision}^{{commit}}")))
        if actual != revision:
            raise ValueError("resolution must name an exact existing commit")
        marker = merge_marker(merge)
        if merge.trial_root.exists():
            raise ValueError("resolution trial is already present; inspect it before proceeding")
        write_json_atomically(marker, merge_authority(merge))
        git(GitCommand(root, ("worktree", "add", "--detach", str(merge.trial_root), revision)))
        candidate = GitMerge().prepare(merge)
        if candidate.revision != revision:
            raise ValueError("resolution checkout differs from its submitted commit")
        return candidate


class MergePreparationFlow:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def prepare(self, request: tuple[ManagementRequest, MergeKind]) -> MergeRecord:
        management, kind = request
        try:
            with self.dependencies.store.locked((management.project_id, "integration")):
                if kind == MergeKind.SYNCHRONIZATION:
                    unchanged = unchanged_sync(self.dependencies, management)
                    if unchanged is not None:
                        return unchanged
                operation = MergePreparation(self.dependencies).pin(request)
        except ValueError as error:
            if kind != MergeKind.SYNCHRONIZATION:
                raise
            return self._deferred((management, None), error)
        result = CandidateEvaluation(self.dependencies).evaluate(operation)
        if result.kind == MergeKind.SYNCHRONIZATION and result.status == MergeStatus.VALIDATED:
            try:
                with self.dependencies.store.locked((management.project_id, "integration")):
                    return self._publish_sync((result, management))
            except ValueError as error:
                return self._deferred((management, result), error)
        return result

    def _deferred(self, request: tuple[ManagementRequest, MergeRecord | None], error: ValueError) -> MergeRecord:
        if not isinstance(error.__cause__, BlockingIOError):
            raise error
        management, operation = request
        deps = self.dependencies
        parent = deps.parentenv.repo.load(management.project_id)
        identity = RecordIdentity(management.project_id, management.delivery_id)
        if parent is None:
            raise ValueError("unknown synchronization application")
        delivery = deps.store.update_delivery((identity,
            lambda value: pending_sync_update(deps, (value, False))))
        if operation is None:
            operation = MergeRecord(uuid4().hex, management.project_id, management.delivery_id,
                MergeKind.SYNCHRONIZATION, delivery.pending_sync_revision or parent.trusted_base_sha,
                delivery.trusted_revision)
        deferred = replace(operation, status=MergeStatus.DEFERRED,
            reason="integration management is publishing/snapshotting; synchronization remains pending")
        deps.store.save_merge(deferred)
        return deferred

    def _publish_sync(self, request: tuple[MergeRecord, ManagementRequest]) -> MergeRecord:
        result, management = request
        context = MergeAuthority(self.dependencies).load(result)
        try:
            MergeApprovals(self.dependencies).current(context)
        except ValueError as error:
            stale = replace(result, status=MergeStatus.STALE, reason=str(error))
            self.dependencies.store.save_merge(stale)
            clear_pending_sync(self.dependencies, stale)
            return stale
        approval = ManagementApproval(result.id, management.actor_reference, result.main_revision,
            result.delivery_revision, result.candidate_revision or "", authority_digest(context))
        approved = replace(result, status=MergeStatus.APPROVED, approval=approval)
        self.dependencies.store.save_merge(approved)
        return MergePublication(self.dependencies).publish(PublicationInput(
            replace(context, operation=approved), approval))


class ResolutionManagement:
    def __init__(self, dependencies: MergeDependencies):
        self.dependencies = dependencies

    def validate(self, identity: RecordIdentity, revision: str) -> MergeRecord:
        deps = self.dependencies
        operation = deps.store.merge(identity)
        if operation is None or operation.status not in {MergeStatus.CONFLICT, MergeStatus.FAILED}:
            raise ValueError("explicit resolution requires a retained conflict or failed candidate")
        with deps.store.locked((identity.project_id, "worker-" + operation.delivery_id)):
            delivery = required_delivery(deps, RecordIdentity(identity.project_id, operation.delivery_id))
            if operation.kind == MergeKind.SYNCHRONIZATION and delivery.phase not in PUBLIC_SYNCHRONIZATION_PHASES:
                return MergeManagement(deps)._deferred(ManagementRequest(
                    identity.project_id, operation.delivery_id, "management-conflict-resolution"))
            with deps.store.locked((identity.project_id, "integration")):
                current = deps.store.merge(identity)
                if current != operation:
                    raise ValueError("conflict-resolution request changed while acquiring ownership")
                context = MergeAuthority(deps).load(operation)
                MergeApprovals(deps).current(context)
                prior = deps.store.directory(identity.project_id) / "validation" / f"{operation.id}-prior-{uuid4().hex}.json"
                write_json_atomically(prior, operation.to_dict())
                reviewed = replace(operation, approval=None, publication_intent=False, candidate_revision=None,
                    conflicts=(), evidence_refs=(*operation.evidence_refs, str(prior)))
            return CandidateEvaluation(deps).evaluate(reviewed, revision)
