"""Outer composition over existing setup and standard branch delivery management."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.delivery_management.composition import TeamCompositionRequest, TeamServices, compose_team_management
from core.delivery_management.dispatch import DeliveryExecutor
from core.delivery_management.domain import DispatchPolicy
from core.delivery_management.service import TeamDeliveryService
from core.project_setup.architecture import PinnedArchitectureApproval
from core.project_setup.commands import SetupCommandRunner
from core.project_setup.profiles import SetupProfileResolver
from core.project_setup.records import ProjectSetupRepository
from core.project_setup.service import ApprovedProjectSetup, ExistingProjects, SetupDependencies
from core.project_setup.workspace import ProjectSetupWorkspace


@dataclass(frozen=True)
class ProjectSetupCompositionRequest:
    state_root: Path
    projects: ExistingProjects
    approvals: PinnedArchitectureApproval
    executor: DeliveryExecutor | None = None
    dispatch_policy: DispatchPolicy = DispatchPolicy()


@dataclass(frozen=True)
class ProjectSetupComposition:
    setup: ApprovedProjectSetup
    deliveries: TeamDeliveryService
    records: ProjectSetupRepository
    management: TeamServices


def compose_project_setup(request: ProjectSetupCompositionRequest) -> ProjectSetupComposition:
    root = request.state_root.resolve()
    records = ProjectSetupRepository(root / "projects")
    runner = SetupCommandRunner()
    workspace = ProjectSetupWorkspace(records.root, runner)
    setup = ApprovedProjectSetup(SetupDependencies(
        request.projects, records, workspace, request.approvals, runner, SetupProfileResolver()))
    management = compose_team_management(TeamCompositionRequest(
        root, request.projects, request.approvals, request.executor, request.dispatch_policy))
    return ProjectSetupComposition(setup, TeamDeliveryService(management), records, management)
