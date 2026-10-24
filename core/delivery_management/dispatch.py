"""Bounded independent workers; project-wide metadata locks never span model work."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from dataclasses import asdict, dataclass, replace
from pathlib import Path
import traceback
from typing import Protocol, Callable
from core.development.feature_management_checkpoint import FeatureManagementCheckpoint
from uuid import uuid4

from core.delivery_management.admission import BranchAdmission
from core.delivery_management.authority_store import AuthorityStore
from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
from core.delivery_management.domain import DeliveryPhase, DispatchPolicy, TeamDelivery
from core.delivery_management.git_workspaces import GitCommand, GitWorkspaces, git
from core.delivery_management.store import ManagementStore, RecordIdentity
from core.project_setup.delivery import DeliveryRequest


@dataclass(frozen=True)
class DispatchRequest:
    delivery: DeliveryRequest
    resume: bool = False


class DeliveryExecutor(Protocol):
    async def deliver(self, request): ...


@dataclass(frozen=True)
class DispatchDependencies:
    admission: BranchAdmission
    records: ManagementStore
    executor: DeliveryExecutor
    checkpoint_factory: Callable[[tuple[RecordIdentity, str]], FeatureManagementCheckpoint | None]
    policy: DispatchPolicy = DispatchPolicy()
    quiescent_sync: Callable[[TeamDelivery], TeamDelivery] | None = None


class BranchDispatch:
    def __init__(self, dependencies: DispatchDependencies):
        self.dependencies = dependencies
        self.capacity = asyncio.Semaphore(dependencies.policy.max_concurrency)

    async def dispatch(self, request: DispatchRequest) -> TeamDelivery:
        record = await self.dependencies.admission.prepare(request.delivery)
        key = RecordIdentity(record.project_id, record.id)
        if record.phase in {DeliveryPhase.COMPLETE, DeliveryPhase.RUNNING} and not request.resume:
            return record
        async with self.capacity:
            with ExitStack() as stack:
                try:
                    stack.enter_context(self.dependencies.records.locked((record.project_id, "worker-" + record.id)))
                except ValueError:
                    return self.dependencies.records.delivery(key) or record
                record = self.dependencies.records.delivery(key) or record
                if record.phase == DeliveryPhase.COMPLETE:
                    return record
                if record.phase != DeliveryPhase.READY and not request.resume:
                    return record
                result = await run_owned(self.dependencies, record)
        if (result.phase == DeliveryPhase.COMPLETE and result.pending_sync
                and self.dependencies.quiescent_sync is not None):
            result = await asyncio.to_thread(self.dependencies.quiescent_sync, result)
        return result


async def run_owned(deps: DispatchDependencies, record: TeamDelivery) -> TeamDelivery:
    from core.delivery_management.bde import BdeDispatch
    key = RecordIdentity(record.project_id, record.id)
    token = uuid4().hex
    deps.records.update_delivery((key, lambda value: replace(
        value, phase=DeliveryPhase.RUNNING, worker_token=token, reason=None, traceback=None)))
    environment = BranchEnvironment(BranchEnvironmentBinding(
        deps.admission.dependencies.parent, deps.records, key))
    cancelled = False
    try:
        environment.recover_behavioral_checkpoint()
        verify_scope(deps.records.delivery(key) or record)
        checkpoint = deps.checkpoint_factory((key, token))
        work = BdeDispatch(deps.records.delivery(key) or record, environment, checkpoint)
        task = asyncio.create_task(asyncio.to_thread(execute_worker, (deps.executor, work)))
        while True:
            try:
                outcome = await asyncio.shield(task)
                break
            except asyncio.CancelledError:
                if task.done():
                    raise
                cancelled = True
        current = deps.records.delivery(key) or record
        verify_scope(current)
        artifact = None
        if outcome.phase == DeliveryPhase.COMPLETE:
            contribution = outcome.contribution
            if (contribution is None or contribution.project_id != record.project_id
                    or contribution.delivery_id != record.id
                    or contribution.source_sha256 != record.behavior.source_sha256
                    or contribution.architecture_sha256 != record.architecture_sha256
                    or contribution.completion_revision != current.trusted_revision):
                raise ValueError("branch completion lacks exact actual accepted authority")
            artifact = AuthorityStore(deps.records).save(contribution)
        def finish(value: TeamDelivery) -> TeamDelivery:
            if value.worker_token != token:
                raise ValueError("delivery worker ownership changed")
            return replace(value, phase=outcome.phase, worker_token=None,
                completion_revision=value.trusted_revision if artifact else value.completion_revision,
                authority_file=artifact.path if artifact else value.authority_file,
                authority_sha256=artifact.sha256 if artifact else value.authority_sha256,
                evidence_refs=outcome.evidence_refs, naming=outcome.naming,
                refactoring=outcome.refactoring, reason=outcome.reason,
                unproven_assurance=tuple(asdict(item) for item in outcome.contribution.unproven_assurance)
                    if outcome.contribution else value.unproven_assurance)
        result = deps.records.update_delivery((key, finish))
    except Exception as error:
        trace = traceback.format_exc()
        def fail(value: TeamDelivery) -> TeamDelivery:
            if value.worker_token != token:
                raise ValueError("cannot release a different delivery worker")
            return replace(value, phase=DeliveryPhase.FAILED, worker_token=None,
                reason=type(error).__name__ + ": " + str(error), traceback=trace)
        result = deps.records.update_delivery((key, fail))
    if cancelled:
        raise asyncio.CancelledError
    return result


def execute_worker(request: tuple[DeliveryExecutor, object]):
    executor, dispatch = request
    return asyncio.run(executor.deliver(dispatch))


def verify_scope(record: TeamDelivery) -> None:
    root = Path(record.worktree)
    GitWorkspaces().require_clean(root)
    if git(GitCommand(root, ("symbolic-ref", "HEAD"))) != record.branch_ref:
        raise ValueError("delivery checkout switched branches")
    if git(GitCommand(root, ("rev-parse", "HEAD"))) != record.trusted_revision:
        raise ValueError("delivery branch is outside its trusted revision")
    changes = git(GitCommand(root, ("diff", "--name-only", "-z",
        record.scope_base_revision or record.fork_revision, record.trusted_revision))).split("\0")
    allowed = {*record.behavior.production_paths, *record.behavior.test_paths}
    if any(path not in allowed for path in changes if path):
        raise ValueError("delivery changed files outside its authorized scope")
