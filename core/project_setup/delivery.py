"""Sequential outer delivery accounting, including the frozen-engine capability gap."""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import traceback
import subprocess
from typing import Protocol

from core.project_setup.architecture import ApprovedArchitecture, FullBehavior, PinnedArchitectureApproval
from core.project_setup.records import DeliveryRecord, DeliveryStatus, ProjectSetupRepository, SetupStatus
from core.project_setup.service import SHARED_BDE_BLOCKER, ExistingProjects
from core.project_setup.workspace import ProjectSetupWorkspace


ACCEPTED = frozenset((DeliveryStatus.COMPLETE, DeliveryStatus.COMPLETE_WITH_UNPROVEN_ASSURANCE))


@dataclass(frozen=True)
class BehaviorDispatch:
    project_id: str
    behavior: FullBehavior
    run_id: str
    architecture_sha256: str
    entry_revision: str
    repository_root: str
    state_namespace: str


@dataclass(frozen=True)
class BdeOutcome:
    status: DeliveryStatus
    last_trusted_revision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    unproven_assurance: tuple[str, ...] = ()
    naming: str | None = None
    refactoring: str | None = None
    reason: str | None = None
    reservation_ids: tuple[str, ...] = ()
    work_ids: tuple[str, ...] = ()


class BehaviorDeliveryPort(Protocol):
    def unsupported_reason(self, request: BehaviorDispatch) -> str | None: ...
    async def deliver(self, request: BehaviorDispatch) -> BdeOutcome: ...


class FrozenSharedProjectBde:
    """No pretending namespaced stores repair the frozen full-lifecycle identity seam."""
    def unsupported_reason(self, request: BehaviorDispatch) -> str | None:
        return SHARED_BDE_BLOCKER

    async def deliver(self, request: BehaviorDispatch) -> BdeOutcome:
        raise ValueError(SHARED_BDE_BLOCKER)


@dataclass(frozen=True)
class DeliveryDependencies:
    records: ProjectSetupRepository
    workspace: ProjectSetupWorkspace
    engine: BehaviorDeliveryPort
    state_root: Path
    projects: ExistingProjects
    approvals: PinnedArchitectureApproval


@dataclass(frozen=True)
class DeliveryRequest:
    handoff: ApprovedArchitecture
    behavior_id: str


class ProjectBehaviorDeliveries:
    def __init__(self, dependencies: DeliveryDependencies):
        self.dependencies = dependencies

    async def dispatch(self, request: DeliveryRequest) -> DeliveryRecord:
        deps = self.dependencies
        decision = request.handoff.decision
        deps.approvals.require(request.handoff)
        parent = await deps.projects.get_project_by_id(decision.project_id)
        if parent is None or str(parent.id) != decision.project_id:
            raise ValueError("delivery requires the existing user-facing project")
        behavior = next((item for item in decision.behaviors if item.id == request.behavior_id), None)
        if behavior is None:
            raise ValueError("unknown project full behavior")
        with deps.records.locked(decision.project_id):
            setup = deps.records.load(decision.project_id)
            if (setup is None or setup.status != SetupStatus.READY or not setup.environment_verified
                    or setup.architecture_sha256 != decision.digest):
                raise ValueError("matching approved project environment is not ready")
            existing = next((item for item in setup.deliveries if item.behavior_id == behavior.id), None)
            if existing:
                return existing
            if setup.active_delivery:
                raise ValueError("another delivery is already active")
            if any((item.repository_progressed or item.repository_uncertain) and item.status not in ACCEPTED for item in setup.deliveries):
                raise ValueError("incomplete BDE progress has no safe cross-delivery continuation boundary")
            prior_ids = [item.id for item in decision.behaviors][:list(decision.behaviors).index(behavior)]
            attempted = {item.behavior_id for item in setup.deliveries
                         if item.status not in (DeliveryStatus.PENDING, DeliveryStatus.RUNNING)}
            if not set(prior_ids) <= attempted:
                raise ValueError("approved sequential delivery order has not reached this behavior")
            accepted = {item.behavior_id for item in setup.deliveries if item.status in ACCEPTED}
            if not set(behavior.depends_on) <= accepted:
                raise ValueError("full behavior dependencies are not satisfied")
            project = deps.workspace.verify(decision.project_id)
            if project.trusted_base_sha != setup.last_accepted_revision:
                raise ValueError("project has intermediate progress outside its fully accepted baseline")
            identity = sha256((decision.project_id + ":" + behavior.id + ":" + decision.digest).encode()).hexdigest()
            run_id = "delivery-" + identity
            dispatch = BehaviorDispatch(decision.project_id, behavior, run_id, decision.digest,
                                       project.trusted_base_sha, project.repository_root,
                                       str(deps.state_root / "deliveries" / identity))
            record = DeliveryRecord(behavior.id, run_id, behavior.source_sha256, decision.digest,
                                    project.trusted_base_sha, DeliveryStatus.RUNNING)
            unsupported = deps.engine.unsupported_reason(dispatch)
            if unsupported:
                blocked = replace(record, status=DeliveryStatus.BLOCKED, reason=unsupported)
                deps.records.save(replace(setup, deliveries=(*setup.deliveries, blocked)))
                return blocked
            deps.records.save(replace(setup, active_delivery=run_id, deliveries=(*setup.deliveries, record)))
            try:
                outcome = await deps.engine.deliver(dispatch)
                current = deps.workspace.verify_delivery((decision.project_id, record.entry_revision,
                                                          (*behavior.production_paths, *behavior.test_paths)))
                if outcome.status in (DeliveryStatus.RUNNING, DeliveryStatus.PENDING):
                    raise ValueError("BDE returned without a terminal or waiting outcome")
                if outcome.status in ACCEPTED and outcome.last_trusted_revision != current.trusted_base_sha:
                    raise ValueError("BDE completion revision disagrees with canonical project authority")
                if outcome.status in ACCEPTED:
                    deps.workspace.verify_regression(decision.project_id)
                record = replace(
                    record, status=outcome.status, last_trusted_bde_revision=outcome.last_trusted_revision,
                    accepted_revision=current.trusted_base_sha if outcome.status in ACCEPTED else None,
                    evidence_refs=outcome.evidence_refs, unproven_assurance=outcome.unproven_assurance,
                    naming=outcome.naming, refactoring=outcome.refactoring, reason=outcome.reason,
                    reservation_ids=outcome.reservation_ids, work_ids=outcome.work_ids,
                    repository_progressed=current.trusted_base_sha != record.entry_revision,
                    observed_repository_revision=current.trusted_base_sha,
                )
            except Exception as error:
                record = _failed_delivery(_FailedDelivery(deps.workspace, decision.project_id, record, error))
            final = replace(setup, active_delivery=None, deliveries=(*setup.deliveries, record),
                            last_accepted_revision=record.accepted_revision or setup.last_accepted_revision)
            deps.records.save(final)
            return record


@dataclass(frozen=True)
class _FailedDelivery:
    workspace: ProjectSetupWorkspace
    project_id: str
    record: DeliveryRecord
    error: Exception


def _failed_delivery(request: _FailedDelivery) -> DeliveryRecord:
    workspace, record, error = request.workspace, request.record, request.error
    observed = workspace.current_revision(request.project_id)
    try:
        trusted = workspace.verify(request.project_id).trusted_base_sha
    except (ValueError, OSError, subprocess.CalledProcessError):
        trusted = None
    return replace(record, status=DeliveryStatus.FAILED, reason=type(error).__name__ + ": " + str(error),
                   traceback=traceback.format_exc(), last_trusted_bde_revision=trusted or record.entry_revision,
                   observed_repository_revision=observed, repository_uncertain=trusted is None,
                   repository_progressed=observed is not None and observed != record.entry_revision)
