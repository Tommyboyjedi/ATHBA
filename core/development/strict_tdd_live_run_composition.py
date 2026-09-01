"""Live-compatible composition root for the durable strict-TDD runner."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from subprocess import run

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
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


@dataclass(frozen=True)
class StrictTddLiveRunConfiguration:
    state_root: Path
    evidence_root: Path
    repository_root: Path
    workload_id: str
    reasoning_model: str = "local-primary"
    athba_revision: str | None = None
    rack_ai_revision: str | None = None


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

    def __init__(self, versions: GitRevisionSource | None = None):
        self.versions = versions or GitRevisionSource()

    def build(self, request: StrictTddLiveRunCompositionRequest) -> StrictTddLiveRunComposition:
        config = request.configuration
        reasoning = request.reasoning_gateway or self._live_reasoning(config)
        feature = StrictTddFeatureCompositionFactory().build(
            StrictTddCompositionRequest(
                config.state_root,
                config.repository_root,
                config.workload_id,
                reasoning,
                request.execution_gateway,
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
            )
        )
        return StrictTddLiveRunComposition(
            controller,
            config.athba_revision or self.versions.resolve(config.repository_root),
            config.rack_ai_revision or self.versions.resolve(Path("/srv/rack-ai")),
        )

    def _live_reasoning(self, config: StrictTddLiveRunConfiguration) -> ReasoningGateway:
        policy = ProviderRetryPolicy(timeout=300.0, max_retries=1, backoff_factor=2.0)
        return ProviderReasoningGateway(OpenAIProvider(policy=policy), config.reasoning_model)
