"""Standard project-management composition over existing setup and BDE capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.development.consolidation_language import ConsolidationLanguage
from core.development.deterministic_regression import SubprocessProjectRuntimeExecutor
from core.development.post_behavior_authority import PythonPostBehaviorAuthority
from core.development.post_behavior_git import PostBehaviorGit
from core.development.post_behavior_slice import PythonProductionSlice
from core.development.post_behavior_validation import PostBehaviorCandidateAuthority, PostBehaviorSource
from core.development.project_environment import ProjectEnvironmentService
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.python_test_material import PythonTestMaterial
from core.delivery_management.admission import AdmissionDependencies, BranchAdmission
from core.delivery_management.bde import StandardBehaviorExecutor
from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
from core.delivery_management.checkpoint import CheckpointBinding, CheckpointDependencies, ManagedCheckpoint
from core.delivery_management.dispatch import BranchDispatch, DeliveryExecutor, DispatchDependencies
from core.delivery_management.domain import DispatchPolicy, ManagementRequest
from core.delivery_management.evidence import AcceptedContribution, CompletedEvidenceLoader, CompletedEvidenceRequest
from core.delivery_management.merge_service import MergeDependencies, MergeManagement
from core.delivery_management.store import ManagementStore
from core.delivery_management.validation import IntegrationValidationDependencies, IntegrationValidator
from core.project_setup.architecture import PinnedArchitectureApproval
from core.project_setup.records import ProjectSetupRepository
from core.project_setup.service import ExistingProjects


@dataclass(frozen=True)
class TeamCompositionRequest:
    state_root: Path
    projects: ExistingProjects
    approvals: PinnedArchitectureApproval
    executor: DeliveryExecutor | None = None
    policy: DispatchPolicy = DispatchPolicy()


@dataclass(frozen=True)
class TeamServices:
    admission: BranchAdmission
    dispatch: BranchDispatch
    merges: MergeManagement
    records: ManagementStore
    parent_environment: ProjectEnvironmentService


def load_python_checkpoint(request: CompletedEvidenceRequest) -> AcceptedContribution:
    project = request.prepared_environment.repo.load(request.project_id)
    if project is None:
        raise ValueError("checkpoint project authority is unavailable")
    source = PostBehaviorSource(PostBehaviorGit(Path(project.repository_root)), PythonProductionSlice())
    loader = CompletedEvidenceLoader(PythonTestMaterial(), PostBehaviorCandidateAuthority(
        source, PythonPostBehaviorAuthority()))
    return loader.load_checkpoint(request)


def compose_team_management(request: TeamCompositionRequest) -> TeamServices:
    parent = ProjectEnvironmentService(request.state_root / "projects")
    records = ManagementStore(parent.root)
    admission = BranchAdmission(AdmissionDependencies(request.projects, request.approvals,
        ProjectSetupRepository(parent.root), parent, records))
    material = PythonTestMaterial()
    validator = IntegrationValidator(IntegrationValidationDependencies(
        material, ConsolidationLanguage(PythonPytestAdapter(), material), SubprocessProjectRuntimeExecutor()))
    merges = MergeManagement(MergeDependencies(records, parent, validator))
    def checkpoint(binding):
        identity, token = binding
        environment = BranchEnvironment(BranchEnvironmentBinding(parent, records, identity))
        return ManagedCheckpoint(CheckpointDependencies(records, merges, load_python_checkpoint),
                                 CheckpointBinding(identity, token, environment))
    def finish_pending(delivery):
        merges.request_sync(ManagementRequest(delivery.project_id, delivery.id, "delivery-management"))
        from core.delivery_management.store import RecordIdentity
        return records.delivery(RecordIdentity(delivery.project_id, delivery.id)) or delivery
    dispatch = BranchDispatch(DispatchDependencies(
        admission, records, request.executor or StandardBehaviorExecutor(), checkpoint,
        request.policy, finish_pending))
    return TeamServices(admission, dispatch, merges, records, parent)
