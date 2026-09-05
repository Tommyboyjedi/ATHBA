"""Reusable composition root for the strict-TDD feature path."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.behavior_completion import BehaviorCompletionDependencies, BehaviorCompletionService
from core.development.behavior_contract_coordinator import BehaviorContractPlanner
from core.development.behavior_repair import (
    BehaviorRepairDependencies,
    BehaviorRepairService,
    BehaviorRepairWorkUnitFactory,
)
from core.development.behavior_repair_git import BehaviorRepairGitCandidateRepository
from core.development.deterministic_regression import DeterministicRegressionService, SubprocessProjectRuntimeExecutor
from core.development.microcycle_domain import LanguageAdapterCatalog
from core.development.microcycle_revision_git import MicrocycleGitClient
from core.development.microcycle_revision_service import MicrocycleRevisionLifecycle, RevisionLifecycleDependencies
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.project_environment import ProjectEnvironmentService
from core.development.provider_behavior_reviewer import ProviderSeniorBehaviorReviewer
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.scenario_drafting import GitCandidateScenarioSourceReader, ScenarioDraftingDependencies, ScenarioDraftingService, ScenarioIntentReviewer
from core.development.scenario_drafting import ScenarioDraftWorkUnitFactory
from core.development.specification_assessment import SpecificationGatekeeper
from core.development.specification_reconciliation import CompletedMicrocycleEvidenceCollector
from core.development.strict_microcycle import (
    DeveloperFrontierWorkUnitFactory,
    GitFrontierMaterialiser,
    RegressionRepairWorkUnitFactory,
    StrictMicrocycleDependencies,
    StrictMicrocycleService,
)
from core.development.strict_tdd_execution_budget import StrictTddExecutionBudgetPolicy
from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService, StrictTddFeatureDependencies
from core.development.strict_tdd_feature_execution import CompletedFeatureReconciler, StrictFeatureScenarioDependencies, StrictFeatureScenarioExecutor
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.athba_workspace_routing import AthbaExecutionProfileResolver
from core.execution.profiled_workspace_gateway import ProfiledWorkspaceExecutionGateway, ProfiledWorkspaceGatewayDependencies
from core.execution.rack_ai_workspace_cli_transport import RackAiWorkspaceCliConfig, RackAiWorkspaceCliTransport
from core.execution.rack_ai_workspace_connector import RackAiWorkspaceConnector
from core.execution.reasoning_gateway import ReasoningGateway
from core.execution.work_unit_gateway import WorkUnitExecutionGateway

@dataclass(frozen=True)
class StrictTddCompositionRequest:
    state_root: Path
    repository_root: Path
    workload_id: str
    reasoning_gateway: ReasoningGateway
    execution_gateway: WorkUnitExecutionGateway | None = None
    execution_budget_policy: StrictTddExecutionBudgetPolicy = field(
        default_factory=StrictTddExecutionBudgetPolicy
    )

@dataclass(frozen=True)
class StrictTddFeatureComposition:
    application: StrictTddFeatureApplicationService
    environment: ProjectEnvironmentService
    revisions: MicrocycleRevisionLifecycle
    rack_ai: WorkUnitExecutionGateway
    behavior_planner: BehaviorContractPlanner
    gatekeeper: SpecificationGatekeeper
    scenario_drafting: ScenarioDraftingService
    adapters: LanguageAdapterCatalog
    microcycles: StrictMicrocycleService
    regression: DeterministicRegressionService
    behavior_completion: BehaviorCompletionService
    behavior_repair: BehaviorRepairService
    completed_evidence: CompletedMicrocycleEvidenceCollector

class StrictTddFeatureCompositionFactory:
    """Wires ports and existing strict-TDD services without endpoint credentials."""
    def build(self, request: StrictTddCompositionRequest) -> StrictTddFeatureComposition:
        root = request.state_root.resolve()
        if request.execution_gateway is None:
            gateway: WorkUnitExecutionGateway = ProfiledWorkspaceExecutionGateway(
                ProfiledWorkspaceGatewayDependencies(
                    RackAiWorkspaceConnector(RackAiWorkspaceCliTransport(RackAiWorkspaceCliConfig())), AthbaExecutionProfileResolver()
                )
            )
        else:
            gateway = request.execution_gateway
        environment = ProjectEnvironmentService(root / "projects")
        adapters = LanguageAdapterCatalog((PythonPytestAdapter(),))
        microcycle_store = MicrocycleStateRepo(root / "microcycles")
        regression = DeterministicRegressionService(SubprocessProjectRuntimeExecutor())
        candidates = GitFrontierMaterialiser()
        completion = BehaviorCompletionService(BehaviorCompletionDependencies(ProviderSeniorBehaviorReviewer(request.reasoning_gateway)))
        repair = BehaviorRepairService(
            BehaviorRepairDependencies(
                microcycle_store,
                BehaviorRepairGitCandidateRepository(candidates),
                gateway,
                regression,
                BehaviorRepairWorkUnitFactory(request.execution_budget_policy),
            )
        )
        strict = StrictMicrocycleService(
            StrictMicrocycleDependencies(
                microcycle_store,
                candidates,
                gateway,
                adapters,
                regression,
                developer_factory=DeveloperFrontierWorkUnitFactory(
                    request.execution_budget_policy
                ),
                regression_repair_factory=RegressionRepairWorkUnitFactory(
                    request.execution_budget_policy
                ),
                behavior_completion=completion,
                behavior_repair=repair,
            )
        )
        drafting = ScenarioDraftingService(
            ScenarioDraftingDependencies(
                gateway,
                ScenarioIntentReviewer(request.reasoning_gateway),
                adapters,
                GitCandidateScenarioSourceReader(request.repository_root),
                ScenarioDraftStateRepo(root / "scenario-drafts"),
                ScenarioDraftWorkUnitFactory(
                    budget_policy=request.execution_budget_policy
                ),
            )
        )
        revisions = MicrocycleRevisionLifecycle(RevisionLifecycleDependencies(MicrocycleRevisionRepository(root / "revisions"), MicrocycleGitClient(request.repository_root)))
        scenarios = StrictFeatureScenarioExecutor(StrictFeatureScenarioDependencies(drafting, strict, revisions, environment))
        reconciler = CompletedFeatureReconciler(request.repository_root, microcycle_store, request.reasoning_gateway)
        application = StrictTddFeatureApplicationService(StrictTddFeatureDependencies(environment, StrictTddFeatureRepository(root / "features"), BehaviorContractPlanner(request.reasoning_gateway), SpecificationGatekeeper(request.reasoning_gateway), scenarios, reconciler))
        return StrictTddFeatureComposition(application, environment, revisions, gateway, application.contract_planner, application.gatekeeper, drafting, adapters, strict, regression, completion, repair, CompletedMicrocycleEvidenceCollector())
