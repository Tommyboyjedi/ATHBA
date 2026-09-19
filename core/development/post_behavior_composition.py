"""Production continuation from the existing completed strict-TDD feature."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from core.execution.local_only_post_behavior_reasoning import LocalOnlyPostBehaviorReasoning
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.rack_ai_workspace_cli_transport import RackAiWorkspaceCliConfig, RackAiWorkspaceCliTransport
from core.execution.rack_ai_workspace_connector import RackAiWorkspaceConnector
from core.execution.workspace_execution_port import AiWorkspaceExecutionPort


@dataclass(frozen=True)
class PostBehaviorCompositionRequest:
    state_root: Path
    project_id: str
    reasoning: ProviderReasoningGateway
    execution: AiWorkspaceExecutionPort | None = None


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
        delivery = AcceptedBehavioralDeliveryLoader(request.state_root).load(request.project_id)
        repository = PostBehaviorStateRepository(request.state_root / "post-behavior")
        evidence = PostBehaviorEvidenceStore(repository.root / request.project_id / "evidence")
        local = LocalOnlyPostBehaviorReasoning(request.reasoning, PostBehaviorReasoningRecorder(evidence))
        git = PostBehaviorGit(Path(delivery.project.repository_root))
        source = PostBehaviorSource(git)
        authority = PostBehaviorCandidateAuthority(source)
        ports = PostBehaviorPorts(
            PostBehaviorAssessors(PostBehaviorAssessorDependencies(delivery, source, local, evidence)),
            PostBehaviorMutation(PostBehaviorMutationDependencies(delivery, source,
                request.execution or RackAiWorkspaceConnector(RackAiWorkspaceCliTransport(RackAiWorkspaceCliConfig())),
                evidence)),
            PostBehaviorValidators(PostBehaviorTestValidation(delivery, authority, evidence),
                PostBehaviorGatekeeper(PostBehaviorGatekeeperDependencies(delivery, authority, evidence, local))),
            PostBehaviorPromotion(ProjectEnvironmentService(request.state_root / "projects"), git))
        lifecycle = PostBehaviorLifecycle(repository, ports)
        current = lifecycle.start(delivery.entry)
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
