"""Outer composition over existing project services and environment authority."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.project_setup.architecture import PinnedArchitectureApproval
from core.project_setup.commands import SetupCommandRunner
from core.project_setup.delivery import (
    DeliveryDependencies, FrozenSharedProjectBde, ProjectBehaviorDeliveries,
)
from core.project_setup.profiles import SetupProfileResolver
from core.project_setup.records import ProjectSetupRepository
from core.project_setup.service import ApprovedProjectSetup, ExistingProjects, SetupDependencies
from core.project_setup.workspace import ProjectSetupWorkspace


@dataclass(frozen=True)
class ProjectSetupCompositionRequest:
    state_root: Path
    projects: ExistingProjects
    approvals: PinnedArchitectureApproval


@dataclass(frozen=True)
class ProjectSetupComposition:
    setup: ApprovedProjectSetup
    deliveries: ProjectBehaviorDeliveries
    records: ProjectSetupRepository


def compose_project_setup(request: ProjectSetupCompositionRequest) -> ProjectSetupComposition:
    root = request.state_root.resolve()
    records = ProjectSetupRepository(root / "projects")
    runner = SetupCommandRunner()
    workspace = ProjectSetupWorkspace(records.root, runner)
    setup = ApprovedProjectSetup(SetupDependencies(
        request.projects, records, workspace, request.approvals, runner, SetupProfileResolver()))
    deliveries = ProjectBehaviorDeliveries(DeliveryDependencies(
        records, workspace, FrozenSharedProjectBde(), root,
        request.projects, request.approvals))
    return ProjectSetupComposition(setup, deliveries, records)
