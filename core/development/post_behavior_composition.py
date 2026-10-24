"""Production continuation from the existing completed strict-TDD feature."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from core.development.python_parameter_naming import PythonParameterNaming
from core.development.post_behavior_authority import PythonPostBehaviorAuthority
from core.development.post_behavior_slice import PythonProductionSlice
from core.development.python_test_material import PythonTestMaterial
from core.development.python_specification_evidence import PythonSpecificationEvidenceAdapter
from core.development.specification_evidence_policy import SpecificationEvidenceAdapters

from core.development.post_behavior_adapters import (
    PostBehaviorAssessors, PostBehaviorAssessorDependencies, PostBehaviorMutation,
    PostBehaviorMutationDependencies, PostBehaviorReasoningRecorder,
)
from core.development.post_behavior_entry import AcceptedBehavioralDeliveryLoader
from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
from core.development.post_behavior_gatekeeper import PostBehaviorGatekeeper, PostBehaviorGatekeeperDependencies
from core.development.post_behavior_git import PostBehaviorGit, PostBehaviorPromotion
from core.development.post_behavior_lifecycle import PostBehaviorLifecycle
from core.development.post_behavior_ports import PostBehaviorPorts, ReconciliationCheckpoint
from core.development.post_behavior_domain import PostBehaviorState, ValidationEvidence
from core.development.post_behavior_store import PostBehaviorStateRepository
from core.development.post_behavior_validation import (
    PostBehaviorSource, PostBehaviorCandidateAuthority, PostBehaviorTestValidation,
)
from core.development.project_environment import ProjectEnvironmentService
from core.development.project_environment_port import PreparedProjectEnvironment
from core.execution.local_only_post_behavior_reasoning import LocalOnlyPostBehaviorReasoning
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.rack_ai_runtime import RackAiRuntimeClient, RackAiRuntimeConfiguration
from core.execution.rack_ai_reservation import RackAiReservation, runtime_identity
from core.execution.rack_ai_reservation_state import ReservationBinding
from core.execution.rack_ai_scoped_access import RackAiScopedAccess
from core.llm.providers.openai_provider import OpenAIProvider
from core.execution.workspace_execution_port import AiWorkspaceExecutionPort
from core.execution.rack_ai_public_workspace import (
    RackAiPublicWorkEvidenceStore,
    RackAiPublicWorkspaceExecutionPort,
)


@dataclass(frozen=True)
class PostBehaviorCompositionRequest:
    state_root: Path
    project_id: str
    reasoning: ProviderReasoningGateway
    execution: AiWorkspaceExecutionPort | None = None
    prepared_environment: PreparedProjectEnvironment | None = None
    reservation_identity: str | None = None


@dataclass(frozen=True)
class PostBehaviorValidators:
    tests: PostBehaviorTestValidation
    gatekeeper: PostBehaviorGatekeeper

    async def test_candidate(self, state: PostBehaviorState) -> ValidationEvidence:
        return await self.tests.test_candidate(state)

    async def reconcile_candidate(self, state: PostBehaviorState, checkpoint: ReconciliationCheckpoint) -> ValidationEvidence:
        return await self.gatekeeper.reconcile_candidate(state, checkpoint)


class PostBehaviorCompositionFactory:
    """Wire existing provider, regression, Gatekeeper and generic execution capabilities."""

    def build(self, request: PostBehaviorCompositionRequest) -> PostBehaviorLifecycle:
        environment: PreparedProjectEnvironment = request.prepared_environment or ProjectEnvironmentService(request.state_root / "projects")
        delivery = AcceptedBehavioralDeliveryLoader(request.state_root, PythonTestMaterial(), environment).load(request.project_id)
        repository = PostBehaviorStateRepository(request.state_root / "post-behavior")
        evidence = PostBehaviorEvidenceStore(repository.root / request.project_id / "evidence")
        if request.reservation_identity is not None:
            if delivery.feature.delivery_identity != request.reservation_identity:
                raise ValueError("post-behavior reservation differs from its durable delivery identity")
            prior_state = repository.load(delivery.entry.delivery_id)
            access = None if prior_state is None else prior_state.rack_ai
            if access is not None and access.work_id != runtime_identity(request.reservation_identity):
                raise ValueError("historical post-behavior reservation requires explicit compatibility review")
        reservation = None
        execution = request.execution
        if execution is None:
            client = RackAiRuntimeClient(RackAiRuntimeConfiguration.from_env())
            reservation = RackAiReservation(
                client,
                tuple(sorted({request.reasoning.model, "local-coder"})),
            )
            provider = request.reasoning.provider
            if type(provider) is not OpenAIProvider:
                raise ValueError("managed post-behavior reasoning requires the local OpenAI provider")
            provider.runtime_access = RackAiScopedAccess(reservation, request.reasoning.model)
            execution = RackAiPublicWorkspaceExecutionPort(
                client,
                reservation,
                RackAiPublicWorkEvidenceStore(repository.root / request.project_id / "evidence" / "rack-ai-work"),
            )
        local = LocalOnlyPostBehaviorReasoning(request.reasoning, PostBehaviorReasoningRecorder(evidence))
        git = PostBehaviorGit(Path(delivery.project.repository_root))
        source = PostBehaviorSource(git, PythonProductionSlice())
        authority = PostBehaviorCandidateAuthority(source, PythonPostBehaviorAuthority())
        ports = PostBehaviorPorts(
            PostBehaviorAssessors(PostBehaviorAssessorDependencies(delivery, source, local, evidence, PythonParameterNaming())),
            PostBehaviorMutation(PostBehaviorMutationDependencies(delivery, source,
                execution,
                evidence)),
            PostBehaviorValidators(PostBehaviorTestValidation(delivery, authority, evidence),
                PostBehaviorGatekeeper(PostBehaviorGatekeeperDependencies(delivery, authority, evidence, local,
                    PythonTestMaterial(), SpecificationEvidenceAdapters((PythonSpecificationEvidenceAdapter(),))))),
            PostBehaviorPromotion(environment, git))
        lifecycle = PostBehaviorLifecycle(repository, ports)
        current = lifecycle.start(delivery.entry)
        lifecycle.reservation = reservation
        lifecycle.reasoning_service = request.reasoning.model
        if reservation is not None:
            reservation.bind(ReservationBinding(repository,
                request.reservation_identity or delivery.entry.delivery_id,
                delivery.entry.delivery_id if request.reservation_identity is not None else None))
        legal = {current.current_post_behavior_revision}
        active = current.active_pass
        if active is not None and active.candidate is not None and active.tests is not None and active.gatekeeper is not None:
            if active.tests.passed and active.gatekeeper.passed:
                if active.candidate.revision is not None:
                    legal.add(active.candidate.revision)
        canonical = git.command(("rev-parse", "--verify", delivery.project.default_ref)).strip()
        if canonical not in legal or delivery.project.trusted_base_sha not in legal:
            raise ValueError("canonical project state is outside the durable accepted post-behavior chain")
        evidence.record("behaviorally_accepted_delivery", delivery)
        return lifecycle
