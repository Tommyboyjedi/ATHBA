"""Live-compatible composition root for the durable strict-TDD runner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from subprocess import run

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.python_pytest_preflight import PythonProbePreflightError, PythonPytestPreflight
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.strict_tdd_feature_composition import (
    StrictTddCompositionRequest,
    StrictTddFeatureCompositionFactory,
)
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import StrictTddLifecycleEventRepository
from core.development.strict_tdd_run_controller import (
    StrictTddRunController,
    StrictTddRunControllerDependencies,
)
from core.development.strict_tdd_run_reporting import (
    StrictTddEvidenceRepositories,
    StrictTddRunEvidenceSnapshotCollector,
    StrictTddRunReportWriter,
)
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.reasoning_gateway import ReasoningGateway
from core.execution.work_unit_gateway import WorkUnitExecutionGateway
from core.llm.contracts.provider import ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider
from core.execution.rack_ai_runtime import RackAiRuntimeConfiguration, RackAiRuntimeClient
from core.execution.rack_ai_reservation import RackAiReservation
from core.execution.rack_ai_scoped_access import RackAiScopedAccess
from core.execution.rack_ai_workspace_runtime import RackAiWorkspaceRuntime
from core.execution.rack_ai_workspace_connector import RackAiWorkspaceConnector
from core.execution.profiled_workspace_gateway import ProfiledWorkspaceExecutionGateway, ProfiledWorkspaceGatewayDependencies
from core.development.athba_workspace_routing import AthbaExecutionProfileResolver


@dataclass(frozen=True)
class StrictTddLiveRunConfiguration:
    state_root: Path
    evidence_root: Path
    repository_root: Path
    workload_id: str
    reasoning_model: str = "local-primary"
    athba_revision: str | None = None
    rack_ai_revision: str | None = None
    athba_repository_root: Path = Path("/srv/ATHBA")


@dataclass(frozen=True)
class StrictTddLiveRunCompositionRequest:
    configuration: StrictTddLiveRunConfiguration
    reasoning_gateway: ReasoningGateway | None = None
    execution_gateway: WorkUnitExecutionGateway | None = None


@dataclass(frozen=True)
class StrictTddLiveRunComposition:
    controller: StrictTddRunController
    athba_revision: str
    rack_ai_revision: str


class GitRevisionSource:
    """Narrow version boundary; callers receive only a resolved SHA."""

    def resolve(self, repository_root: Path) -> str:
        completed = run(
            ("git", "-C", str(repository_root), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()


class StrictTddLiveRunCompositionFactory:
    """Wires production ports without doing strict-TDD application work."""

    def __init__(self, versions: GitRevisionSource | None = None, preflight: PythonPytestPreflight | None = None):
        self.versions = versions or GitRevisionSource()
        self.preflight = preflight or PythonPytestPreflight()

    def build(self, request: StrictTddLiveRunCompositionRequest) -> StrictTddLiveRunComposition:
        config = request.configuration
        diagnostic = self.preflight.check(config.state_root / "probe-preflight")
        if diagnostic.kind != "green":
            raise PythonProbePreflightError(diagnostic)
        reservation = None
        execution = request.execution_gateway
        reasoning = request.reasoning_gateway
        if execution is None or reasoning is None:
            services = {"local-primary", "local-coder"} if execution is None else set()
            if reasoning is None:
                services.add(config.reasoning_model)
            reservation = RackAiReservation(RackAiRuntimeClient(RackAiRuntimeConfiguration.from_env()), tuple(sorted(services)))
            if execution is None:
                execution = ProfiledWorkspaceExecutionGateway(ProfiledWorkspaceGatewayDependencies(
                    RackAiWorkspaceConnector(RackAiWorkspaceRuntime(reservation)), AthbaExecutionProfileResolver()))
            if reasoning is None:
                reasoning = self._live_reasoning(config, reservation)
        feature = StrictTddFeatureCompositionFactory().build(
            StrictTddCompositionRequest(
                config.state_root,
                config.repository_root,
                config.workload_id,
                reasoning,
                execution,
            )
        )
        lifecycle = StrictTddLifecycleEventRepository(config.state_root / "lifecycle-events")
        evidence = StrictTddEvidenceRepositories(
            StrictTddFeatureRepository(config.state_root / "features"),
            ScenarioDraftStateRepo(config.state_root / "scenario-drafts"),
            MicrocycleStateRepo(config.state_root / "microcycles"),
            MicrocycleRevisionRepository(config.state_root / "revisions"),
            lifecycle,
        )
        controller = StrictTddRunController(
            StrictTddRunControllerDependencies(
                feature.application,
                StrictTddRunStateRepository(config.state_root / "runs"),
                lifecycle,
                StrictTddRunEvidenceSnapshotCollector(evidence),
                StrictTddRunReportWriter(config.evidence_root),
                reservation,
            )
        )
        return StrictTddLiveRunComposition(
            controller,
            config.athba_revision or self.versions.resolve(config.athba_repository_root),
            config.rack_ai_revision or self.versions.resolve(Path("/srv/rack-ai")),
        )

    def _live_reasoning(self, config: StrictTddLiveRunConfiguration, reservation: RackAiReservation) -> ProviderReasoningGateway:
        policy = ProviderRetryPolicy(timeout=300.0, max_retries=1, backoff_factor=2.0)
        provider = OpenAIProvider(policy=policy)
        provider.runtime_access = RackAiScopedAccess(reservation, config.reasoning_model)
        return ProviderReasoningGateway(provider, config.reasoning_model)
