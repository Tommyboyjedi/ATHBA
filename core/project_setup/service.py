"""Approval-first project setup; no BDE orchestration or new project database."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from core.dataclasses.project import Project
from core.project_setup.architecture import ApprovedArchitecture, PinnedArchitectureApproval, content_hash
from core.project_setup.commands import SetupCommandRunner
from core.project_setup.profiles import SetupProfileResolver
from core.project_setup.profile_domain import ResolvedSetupProfile
from core.project_setup.recovery import HistoricalSetupEvidence
from core.project_setup.records import ProjectSetupRecord, ProjectSetupRepository, SetupStatus
from core.project_setup.workspace import ProjectSetupWorkspace, WorkspacePreparation, WorkspaceRecovery


SHARED_BDE_BLOCKER = (
    "Frozen BDE full-lifecycle factories bind feature and post-behavior authority to project_id "
    "and co-located project state. Independent full behaviors cannot share this authority safely "
    "through the current public composition seams."
)


class ExistingProjects(Protocol):
    async def get_project_by_id(self, project_id: str) -> Project | None: ...
    async def get_latest_spec(self, project_id: str) -> dict | None: ...


@dataclass(frozen=True)
class SetupDependencies:
    projects: ExistingProjects
    records: ProjectSetupRepository
    workspace: ProjectSetupWorkspace
    approvals: PinnedArchitectureApproval
    runner: SetupCommandRunner
    profiles: SetupProfileResolver


class ApprovedProjectSetup:
    def __init__(self, dependencies: SetupDependencies):
        self.dependencies = dependencies

    async def prepare(self, handoff: ApprovedArchitecture) -> ProjectSetupRecord:
        deps = self.dependencies
        decision = handoff.decision
        profile = await self._approved_profile(handoff)
        with deps.records.locked(decision.project_id):
            existing = deps.records.load(decision.project_id)
            if existing and existing.architecture_sha256 != decision.digest:
                raise ValueError("incompatible approved architecture; existing setup was not changed")
            if existing is not None:
                deps.records.archive_failure(existing)
            record = existing or ProjectSetupRecord(
                decision.project_id, decision.digest, decision.specification_sha256,
                profile.id, profile.technologies, SetupStatus.BLOCKED,
                behavior_ids=tuple(item.id for item in decision.behaviors),
                behaviors=decision.behaviors,
                approval_identity=handoff.approval.identity,
                approval_kind=handoff.approval.kind.value,
                setup_identity=content_hash({"project": decision.project_id, "architecture": decision.digest}),
                bde_handoff_reason=SHARED_BDE_BLOCKER,
            )
            tools = tuple(deps.runner.inspect((probe, deps.records.root)) for probe in profile.tools)
            missing = tuple(item.kind + "@" + item.expected_version for item in tools if not item.available)
            if missing:
                blocked = replace(record, status=SetupStatus.BLOCKED, environment_verified=False,
                                  tools=tools, reason="missing or incompatible managed tools: " + ", ".join(missing))
                deps.records.save(blocked)
                return blocked
            if profile.verification_limitation:
                blocked = replace(record, status=SetupStatus.BLOCKED, environment_verified=False,
                                  tools=tools, reason=profile.verification_limitation)
                deps.records.save(blocked)
                return blocked
            if existing and existing.status == SetupStatus.READY:
                deps.workspace.prepare(WorkspacePreparation(decision, profile))
                return existing
            try:
                prepared = deps.workspace.prepare(WorkspacePreparation(decision, profile))
            except Exception as error:
                deps.records.save(replace(record, status=SetupStatus.FAILED, environment_verified=False,
                                          tools=tools, commands=tuple(getattr(error, "commands", ())),
                                          reason=type(error).__name__ + ": " + str(error)))
                raise
            ready = replace(
                record, status=SetupStatus.READY, environment_verified=True, tools=tools,
                repository_root=prepared.project.repository_root,
                scaffold_revision=prepared.project.trusted_base_sha,
                last_accepted_revision=record.last_accepted_revision or prepared.project.trusted_base_sha,
                commands=prepared.commands, bde_language_compatible=profile.bde_language_compatible,
                reason=None,
            )
            deps.records.save(ready)
            return ready


    async def recover(self, handoff: ApprovedArchitecture, evidence: HistoricalSetupEvidence) -> ProjectSetupRecord:
        deps = self.dependencies
        profile = await self._approved_profile(handoff)
        with deps.records.locked(handoff.decision.project_id):
            current = deps.records.load(handoff.decision.project_id)
            if (current is None or current.status != SetupStatus.FAILED
                    or current.architecture_sha256 != handoff.decision.digest
                    or current.environment_verified or current.scaffold_revision is not None
                    or current.last_accepted_revision is not None or current.deliveries or current.active_delivery):
                raise ValueError("historical recovery requires this exact failed, undelivered setup")
            deps.records.archive_failure(current)
            deps.workspace.recover(WorkspaceRecovery(
                WorkspacePreparation(handoff.decision, profile), handoff.approval, evidence))
        return await self.prepare(handoff)

    async def _approved_profile(self, handoff: ApprovedArchitecture) -> ResolvedSetupProfile:
        deps, decision = self.dependencies, handoff.decision
        deps.approvals.require(handoff)
        project = await deps.projects.get_project_by_id(decision.project_id)
        if project is None or str(project.id) != decision.project_id:
            raise ValueError("setup requires the existing user-facing project")
        spec = await deps.projects.get_latest_spec(decision.project_id)
        if (spec is None or spec.get("version") != decision.specification_version
                or content_hash(spec.get("content")) != decision.specification_sha256):
            raise ValueError("approved specification version/hash does not match the existing project")
        return deps.profiles.resolve(decision.profile)
