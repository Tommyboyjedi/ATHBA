"""Run the existing behavioral and post-behavior engines in one delivery binding."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.delivery_management.domain import DeliveryPhase, TeamDelivery
from core.delivery_management.evidence import (
    AcceptedContribution, CompletedEvidenceLoader, CompletedEvidenceRequest,
)
from core.development.feature_management_checkpoint import FeatureManagementCheckpoint
from core.development.post_behavior_authority import PythonPostBehaviorAuthority
from core.development.post_behavior_composition import (
    PostBehaviorCompositionFactory, PostBehaviorCompositionRequest,
)
from core.development.post_behavior_domain import (
    PostBehaviorOutcome, PostBehaviorPhase, PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_git import PostBehaviorGit
from core.development.post_behavior_slice import PythonProductionSlice
from core.development.post_behavior_store import PostBehaviorStateRepository
from core.development.post_behavior_validation import PostBehaviorCandidateAuthority, PostBehaviorSource
from core.development.project_environment_port import PreparedProjectEnvironment
from core.development.python_test_material import PythonTestMaterial
from core.development.strict_tdd_live_run_composition import (
    StrictTddLiveRunCompositionFactory, StrictTddLiveRunCompositionRequest,
    StrictTddLiveRunConfiguration,
)
from core.development.strict_tdd_run_domain import (
    StrictTddRunControllerConfig, StrictTddRunMode, StrictTddRunRequest,
    StrictTddRunResult, StrictTddRunStatus,
)
from core.development.strict_tdd_run_store import StrictTddRunStateRepository
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.rack_ai_runtime import RackAiResourceWait
from core.llm.contracts.provider import ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider


DEFAULT_TRANSITION_LIMIT = 1000
DEFAULT_POST_REASONING_TIMEOUT = 300.0
COMPLETE_POST_STATES = frozenset({
    PostBehaviorStatus.POST_BEHAVIOR_COMPLETE,
    PostBehaviorStatus.POST_BEHAVIOR_COMPLETE_WITH_UNPROVEN_ASSURANCE,
})


@dataclass(frozen=True)
class BdeDispatch:
    delivery: TeamDelivery
    environment: PreparedProjectEnvironment
    checkpoint: FeatureManagementCheckpoint | None = None


@dataclass(frozen=True)
class BdeBranchOutcome:
    phase: DeliveryPhase
    contribution: AcceptedContribution | None = None
    evidence_refs: tuple[str, ...] = ()
    naming: str | None = None
    refactoring: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.phase == DeliveryPhase.COMPLETE) != (self.contribution is not None):
            raise ValueError("branch completion requires actual accepted contribution authority")


def _post_reasoning() -> ProviderReasoningGateway:
    # The existing post-behavior CLI policy, instantiated once per delivery.
    provider = OpenAIProvider(policy=ProviderRetryPolicy(
        timeout=DEFAULT_POST_REASONING_TIMEOUT, max_retries=0, backoff_factor=1.0))
    return ProviderReasoningGateway(provider, "local-primary")


@dataclass(frozen=True)
class BehaviorExecutionFactories:
    feature: StrictTddLiveRunCompositionFactory = field(default_factory=StrictTddLiveRunCompositionFactory)
    post: PostBehaviorCompositionFactory = field(default_factory=PostBehaviorCompositionFactory)
    post_reasoning: Callable[[], ProviderReasoningGateway] = _post_reasoning


@dataclass(frozen=True)
class BehavioralBranchRunner:
    factories: BehaviorExecutionFactories

    async def run(self, request: BdeDispatch) -> StrictTddRunResult | None:
        record = request.delivery
        root = Path(record.state_root)
        runs = StrictTddRunStateRepository(root / "runs")
        previous = runs.load(record.id)
        if previous is not None and previous.status == StrictTddRunStatus.COMPLETED:
            feature = StrictTddFeatureRepository(root / "features").load(record.project_id)
            if (feature is None or feature.delivery_identity != record.id
                    or feature.source_requirement_hash != record.behavior.source_sha256):
                raise ValueError("completed behavioral run has different delivery/source authority")
            return None
        configuration = StrictTddLiveRunConfiguration(
            root, root / "evidence", Path(record.worktree), record.project_id,
            athba_repository_root=Path(__file__).resolve().parents[2])
        composition = self.factories.feature.build(StrictTddLiveRunCompositionRequest(
            configuration, prepared_environment=request.environment,
            scenario_namespace=record.id, management_checkpoint=request.checkpoint))
        mode = StrictTddRunMode.START if previous is None else StrictTddRunMode.RESUME
        run = StrictTddRunRequest(record.id, record.project_id, record.behavior.source,
            "python", "pytest", record.behavior.production_paths, record.behavior.test_paths,
            root.name, "evidence", mode, None, composition.athba_revision,
            composition.rack_ai_revision, StrictTddRunControllerConfig(DEFAULT_TRANSITION_LIMIT))
        try:
            return await composition.controller.run(run)
        finally:
            reservation = composition.controller.reservation
            if reservation is not None and reservation.binding is not None:
                composition.controller.stop()


@dataclass(frozen=True)
class PostBehaviorBranchRunner:
    factories: BehaviorExecutionFactories

    async def run(self, request: BdeDispatch) -> PostBehaviorState:
        record = request.delivery
        root = Path(record.state_root)
        previous = PostBehaviorStateRepository(root / "post-behavior").load(record.project_id)
        if previous is not None and previous.terminal:
            return previous
        lifecycle = self.factories.post.build(PostBehaviorCompositionRequest(
            root, record.project_id, self.factories.post_reasoning(),
            prepared_environment=request.environment, reservation_identity=record.id))
        try:
            return await lifecycle.run(record.project_id)
        finally:
            reservation = lifecycle.reservation
            if reservation is not None and reservation.binding is not None:
                lifecycle.stop()


@dataclass(frozen=True)
class CompletedBranchContribution:
    def load(self, request: BdeDispatch) -> AcceptedContribution:
        record = request.delivery
        project = request.environment.repo.load(record.project_id)
        if project is None:
            raise ValueError("completed delivery lost its prepared project binding")
        source = PostBehaviorSource(PostBehaviorGit(Path(project.repository_root)), PythonProductionSlice())
        authority = PostBehaviorCandidateAuthority(source, PythonPostBehaviorAuthority())
        return CompletedEvidenceLoader(PythonTestMaterial(), authority).load(CompletedEvidenceRequest(
            Path(record.state_root), record.project_id, record.id, record.behavior.id,
            record.behavior.source_sha256, record.architecture_sha256, request.environment))


class StandardBehaviorExecutor:
    """Compose the existing BDE; branch completion never promotes application main."""

    def __init__(self, factories: BehaviorExecutionFactories | None = None):
        self.factories = factories or BehaviorExecutionFactories()

    async def deliver(self, request: BdeDispatch) -> BdeBranchOutcome:
        evidence: tuple[str, ...] = ()
        try:
            behavioral = await BehavioralBranchRunner(self.factories).run(request)
            if behavioral is not None:
                evidence = tuple(value for value in (
                    behavioral.structured_report_path, behavioral.markdown_report_path) if value)
                if behavioral.status != StrictTddRunStatus.COMPLETED:
                    waiting = behavioral.status == StrictTddRunStatus.RESOURCE_WAITING
                    return BdeBranchOutcome(DeliveryPhase.WAITING if waiting else DeliveryPhase.BLOCKED,
                        evidence_refs=evidence, reason=behavioral.reason or behavioral.status.value)
            post = await PostBehaviorBranchRunner(self.factories).run(request)
        except RackAiResourceWait as error:
            return BdeBranchOutcome(DeliveryPhase.WAITING, evidence_refs=evidence, reason=str(error))
        if post.status not in COMPLETE_POST_STATES:
            return BdeBranchOutcome(DeliveryPhase.BLOCKED, evidence_refs=evidence,
                reason=post.diagnostic or post.status.value)
        contribution = CompletedBranchContribution().load(request)
        return BdeBranchOutcome(DeliveryPhase.COMPLETE, contribution,
            tuple(dict.fromkeys((*evidence, *contribution.provenance_refs))),
            _phase_result(post, PostBehaviorPhase.NAMING),
            _phase_result(post, PostBehaviorPhase.REFACTORING))


def _phase_result(state: PostBehaviorState, phase: PostBehaviorPhase) -> str | None:
    matching = tuple(change for change in state.passes if change.phase == phase)
    if not matching:
        return None
    outcome = matching[-1].outcome
    return "NO" if outcome == PostBehaviorOutcome.NO_CHANGE else outcome.value
