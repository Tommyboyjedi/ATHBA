"""Controlled real-Git proof of the narrow delivery composition seams."""
from dataclasses import replace
from pathlib import Path

import pytest

from core.development.feature_management_checkpoint import (
    FeatureCheckpointResult, management_checkpoint,
)
from core.development.microcycle_revision_state import RevisionInitialisationRequest
from core.development.post_behavior_composition import (
    PostBehaviorCompositionFactory, PostBehaviorCompositionRequest,
)
from core.development.post_behavior_domain import PostBehaviorStatus
from core.development.project_environment import ProjectLoadDisposition, ProjectEnvironmentService
from core.development.strict_tdd_feature_composition import (
    StrictTddCompositionRequest, StrictTddFeatureCompositionFactory,
)
from core.development.strict_tdd_feature_domain import StrictTddFeatureRequest
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from tests.development.test_post_behavior_integration import (
    PROJECT, GenericGitExecution, commit, configured_gateway, gatekeeper_yes,
    git, seeded_delivery,
)
from tests.development.test_strict_tdd_feature_composition import DeterministicReasoning, GitGateway


class BoundRepository:
    def __init__(self, project):
        self.project = project

    def load(self, project_id):
        assert project_id == self.project.project_id
        return self.project

    def save(self, project):
        assert project.project_id == self.project.project_id
        assert project.repository_root == self.project.repository_root
        assert project.default_ref == self.project.default_ref
        assert project.runtime == self.project.runtime
        assert git(Path(project.repository_root), "rev-parse", project.default_ref) == project.trusted_base_sha
        self.project = project


class BoundEnvironment:
    def __init__(self, project, legacy):
        self.repo = BoundRepository(project)
        self.legacy = legacy

    def _git_client(self):
        return self.legacy._git_client()

    def create_or_load_python_project_with_disposition(self, project_id, production_paths=()):
        return ProjectLoadDisposition(self.repo.load(project_id), False)

    def record_trusted_revision(self, project_id, revision):
        raise AssertionError("this fixture exercises existing lifecycle-owned promotion")


def branch_environment(state_root, canonical, workspace, branch):
    legacy = ProjectEnvironmentService(state_root / "projects")
    project = legacy.repo.load(PROJECT)
    git(canonical, "worktree", "add", "-b", branch, str(workspace), project.trusted_base_sha)
    return BoundEnvironment(replace(project, repository_root=str(workspace), default_ref=branch), legacy)


@pytest.mark.asyncio
async def test_real_feature_factory_uses_distinct_persisted_scenario_and_working_refs(tmp_path):
    state_root, canonical, _, baseline = seeded_delivery(tmp_path)
    template = StrictTddFeatureRepository(state_root / "features").load(PROJECT)
    scenarios, refs = [], []
    for name in ("catalogue", "basket"):
        root = tmp_path / name
        workspace = tmp_path / (name + "-workspace")
        environment = branch_environment(state_root, canonical, workspace, "delivery/" + name)
        composition = StrictTddFeatureCompositionFactory().build(StrictTddCompositionRequest(
            root, workspace, name, DeterministicReasoning(), GitGateway(workspace),
            prepared_environment=environment, scenario_namespace=name,
        ))
        composition.application.states.save(replace(template, status="running",
            completed_behaviors=(), final_reconciliation=(), delivery_identity=name,
            canonical_ref="refs/heads/delivery/" + name))
        request = StrictTddFeatureRequest(PROJECT, "selected source", "python", "pytest",
            ("counter.py",), ("tests/test_counter.py",), "managed", "resume", None, str(root))
        result = await composition.application.advance(request)
        scenarios.append(result.result.current_scenario_id)
        revision = composition.revisions.initialise(RevisionInitialisationRequest(
            result.result.current_scenario_id, result.result.canonical_ref, baseline))
        refs.append(revision.working_ref)
        assert composition.environment is environment
        assert composition.application.states.load(PROJECT).delivery_identity == name
        assert not (root / "projects").exists()
        # An old unscoped record cannot silently resume as a scoped delivery.
        composition.application.states.save(replace(template, delivery_identity=None))
        with pytest.raises(ValueError, match="explicit compatibility"):
            await composition.application.advance(request)
    assert scenarios == ["catalogue--B-1", "basket--B-1"]
    assert len(set(refs)) == 2
    assert git(canonical, "rev-parse", "main") == baseline


@pytest.mark.asyncio
async def test_real_post_behavior_loader_and_promotions_keep_application_main_unchanged(tmp_path, monkeypatch):
    state_root, canonical, _, baseline = seeded_delivery(tmp_path)
    workspace = tmp_path / "delivery"
    branch_environment(state_root, canonical, workspace, "delivery/catalogue")
    from hashlib import sha256
    from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
    from core.delivery_management.domain import TeamDelivery
    from core.delivery_management.store import ManagementStore, RecordIdentity
    from core.project_setup.architecture import FullBehavior
    features = StrictTddFeatureRepository(state_root / "features")
    feature = features.load(PROJECT)
    source = feature.contract_payload["requirement_source"]
    source_hash = sha256(source.encode()).hexdigest()
    features.save(replace(feature, canonical_ref="refs/heads/delivery/catalogue",
        delivery_identity="catalogue", source_requirement_hash=source_hash))
    record = TeamDelivery("catalogue", PROJECT, FullBehavior("catalogue", source, source_hash,
        ("counter.py",), ("tests/test_counter.py",)), "architecture", 1, "specification", 1,
        "refs/heads/delivery/catalogue", str(workspace), str(state_root), baseline, baseline, baseline)
    parent = ProjectEnvironmentService(state_root / "projects")
    records = ManagementStore(parent.root)
    records.save_delivery(record)
    environment = BranchEnvironment(BranchEnvironmentBinding(parent, records, RecordIdentity(PROJECT, record.id)))
    gateway, calls = configured_gateway(monkeypatch, [
        "LegacyCounter -> SumCounter", gatekeeper_yes(), "NO",
        "YES\nobjective: Replace duplicated accumulation with one sum calculation.\nreason: Removes an identical loop.",
        gatekeeper_yes(), "NO",
    ])
    execution = GenericGitExecution(workspace, tmp_path)
    request = PostBehaviorCompositionRequest(state_root, PROJECT, gateway, execution, environment)
    for _ in range(30):
        state = await PostBehaviorCompositionFactory().build(request).advance(PROJECT)
        if state.terminal:
            break
    assert state.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE, state.diagnostic
    assert len(calls) == 6 and len(execution.calls) == 2
    assert state.behaviorally_accepted_revision == baseline
    assert environment.repo.load(PROJECT).trusted_base_sha == state.current_post_behavior_revision
    assert git(workspace, "rev-parse", "delivery/catalogue") == state.current_post_behavior_revision
    assert git(canonical, "rev-parse", "main") == baseline
    assert ProjectEnvironmentService(state_root / "projects").repo.load(PROJECT).trusted_base_sha == baseline
    assert all(call.repository.registered_root == str(workspace) for call in execution.calls)


@pytest.mark.asyncio
async def test_management_checkpoint_rebinds_only_quiescent_base_and_preserves_old_evidence(tmp_path):
    state_root, canonical, _, baseline = seeded_delivery(tmp_path)
    environment = branch_environment(state_root, canonical, tmp_path / "delivery", "delivery/catalogue")
    original = StrictTddFeatureRepository(state_root / "features").load(PROJECT)
    quiescent = replace(original, status="running", final_reconciliation=(),
        reconciliation_progress=({"revision": baseline, "immutable": "old checkpoint"},),
        canonical_ref="refs/heads/delivery/catalogue")
    class Checkpoint:
        calls = 0

        async def synchronize(self, request):
            self.calls += 1
            root = Path(environment.repo.project.repository_root)
            (root / "accepted-main.txt").write_text("management-authorized import\n")
            revision = commit(root, "validated main synchronization")
            environment.repo.save(replace(environment.repo.project, trusted_base_sha=revision))
            return FeatureCheckpointResult(revision, ("fresh-regression-validation",))
    checkpoint = Checkpoint()
    active = replace(quiescent, current_scenario_id="catalogue--B-2")
    assert await management_checkpoint(checkpoint, (environment, active)) == active
    assert checkpoint.calls == 0
    synchronized = await management_checkpoint(checkpoint, (environment, quiescent))
    assert checkpoint.calls == 1
    assert synchronized.canonical_development_base != baseline
    assert synchronized.completed_behaviors == original.completed_behaviors
    assert synchronized.completed_behaviors[0].canonical_revision == baseline
    assert synchronized.behavioral_entry_revision == original.behavioral_entry_revision
    assert synchronized.reconciliation_progress == ()
    assert synchronized.reconciliation_history[-1]["revision"] == baseline
    assert synchronized.reconciliation_history[-1]["progress"] == list(quiescent.reconciliation_progress)
    assert synchronized.evidence_refs == (*original.evidence_refs, "fresh-regression-validation")
    assert git(canonical, "rev-parse", "main") == baseline


@pytest.mark.asyncio
async def test_standard_executor_runs_real_bde_to_post_completion_and_reuses_result(tmp_path, monkeypatch):
    import json
    from hashlib import sha256
    from core.delivery_management.bde import (
        BdeDispatch, BehaviorExecutionFactories, StandardBehaviorExecutor,
    )
    from core.delivery_management.domain import DeliveryPhase, TeamDelivery
    from core.development.strict_tdd_live_run_composition import StrictTddLiveRunCompositionFactory
    from core.execution.reasoning_gateway import ReasoningResult
    from core.project_setup.architecture import FullBehavior
    from tests.development.test_strict_tdd_feature_composition import feature_contract

    parent = ProjectEnvironmentService(tmp_path / "parent" / "projects")
    project = parent.create_or_load_python_project(PROJECT, ("widget.py",))
    canonical = Path(project.repository_root)
    workspace = tmp_path / "workspace"
    environment = branch_environment(tmp_path / "parent", canonical, workspace, "delivery/catalogue")
    contract = replace(feature_contract(), project_id=PROJECT, public_api=[])
    source = contract.requirement_source
    behavior = FullBehavior("catalogue", source, sha256(source.encode()).hexdigest(),
        ("widget.py",), ("tests/test_B_1.py",))
    record = TeamDelivery("catalogue-delivery", PROJECT, behavior, "architecture", 1,
        "specification", 1, "refs/heads/delivery/catalogue", str(workspace),
        str(tmp_path / "delivery-state"), project.trusted_base_sha,
        project.trusted_base_sha, project.trusted_base_sha)
    from core.delivery_management.branch_environment import BranchEnvironment, BranchEnvironmentBinding
    from core.delivery_management.store import ManagementStore, RecordIdentity
    records = ManagementStore(parent.root)
    records.save_delivery(record)
    environment = BranchEnvironment(BranchEnvironmentBinding(
        parent, records, RecordIdentity(PROJECT, record.id)))

    class Reasoning:
        def __init__(self):
            self.other = DeterministicReasoning()
            self.purposes = []

        async def reason(self, request):
            self.purposes.append(request.purpose)
            if request.purpose == "athba_source_requirement_clauses":
                payload = {"clauses": [dict(contract.source_clauses[0].to_dict(),
                    source_quote=source, subject=source)]}
            elif request.purpose == "athba_behavior_contract":
                payload = contract.to_dict()
            elif request.purpose == "athba_specification_checklist":
                payload = {"items": [dict(ref="CHK-1", text=source, kind="behavior",
                    modality="required", source_quote=source, subject=source,
                    obligation_type="observable_behavior")]}
            else:
                return await self.other.reason(request)
            return ReasoningResult(json.dumps(payload))

    reasoning = Reasoning()
    execution = GitGateway(workspace)
    post_gateway, provider_calls = configured_gateway(monkeypatch, ["NO", "NO"])
    class FeatureFactory:
        calls = 0

        def build(self, request):
            self.calls += 1
            assert request.prepared_environment is environment
            assert request.scenario_namespace == record.id
            return StrictTddLiveRunCompositionFactory().build(replace(
                request, reasoning_gateway=reasoning, execution_gateway=execution))

    class PostFactory:
        calls = 0

        def build(self, request):
            self.calls += 1
            assert request.prepared_environment is environment
            return PostBehaviorCompositionFactory().build(replace(
                request, execution=GenericGitExecution(workspace, tmp_path)))

    feature, post = FeatureFactory(), PostFactory()
    executor = StandardBehaviorExecutor(BehaviorExecutionFactories(
        feature, post, lambda: post_gateway))
    outcome = await executor.deliver(BdeDispatch(record, environment))
    assert outcome.phase == DeliveryPhase.COMPLETE, outcome.reason
    assert outcome.contribution.completion_revision == environment.repo.load(PROJECT).trusted_base_sha
    assert outcome.contribution.delivery_id == record.id
    assert outcome.contribution.tests[0].test_name == "tests/test_B_1.py::test_B_1"
    assert execution.bindings
    assert all(binding.registered_root == str(workspace) for binding in execution.bindings)
    assert git(canonical, "rev-parse", "main") == project.trusted_base_sha
    before = (len(reasoning.purposes), len(execution.bindings), len(provider_calls))
    assert (await executor.deliver(BdeDispatch(record, environment))).contribution == outcome.contribution
    assert feature.calls == post.calls == 1
    assert before == (len(reasoning.purposes), len(execution.bindings), len(provider_calls))
    # Equal SHAs do not authorize a persisted BDE to target application main.
    features = StrictTddFeatureRepository(Path(record.state_root) / "features")
    accepted_feature = features.load(PROJECT)
    features.save(replace(accepted_feature, canonical_ref="refs/heads/main"))
    with pytest.raises(ValueError, match="source/branch authority"):
        environment.create_or_load_python_project_with_disposition(PROJECT)
    features.save(accepted_feature)
    assert git(canonical, "rev-parse", "main") == project.trusted_base_sha


def test_parallel_post_compositions_keep_distinct_runtime_identity_and_same_local_project_key(tmp_path, monkeypatch):
    from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
    from core.development.post_behavior_store import PostBehaviorStateRepository
    from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
    from core.execution.rack_ai_reservation import runtime_identity
    import core.development.post_behavior_composition as composition_source
    from tests.execution.test_rack_ai_runtime_reservations import Runtime

    state_root, canonical, _, baseline = seeded_delivery(tmp_path)
    original = StrictTddFeatureRepository(state_root / "features").load(PROJECT)
    microcycle = MicrocycleStateRepo(state_root / "microcycles").load("scenario-1")
    runtime = Runtime(tmp_path)
    monkeypatch.setenv("ATHBA_RACK_AI_ORIGIN", runtime.configuration.origin)
    monkeypatch.setenv("ATHBA_RACK_AI_CREDENTIAL_FILE", str(runtime.configuration.credential_file))
    monkeypatch.setattr(composition_source, "RackAiRuntimeClient", lambda config: runtime)
    work_ids = []
    for name in ("catalogue", "basket"):
        root = tmp_path / (name + "-state")
        workspace = tmp_path / (name + "-post-workspace")
        environment = branch_environment(state_root, canonical, workspace, "delivery/" + name)
        StrictTddFeatureRepository(root / "features").save(replace(original,
            canonical_ref="refs/heads/delivery/" + name, delivery_identity=name))
        MicrocycleStateRepo(root / "microcycles").save(microcycle)
        gateway, _ = configured_gateway(monkeypatch, [])
        gateway = ProviderReasoningGateway(gateway.provider, "local-primary")
        request = PostBehaviorCompositionRequest(root, PROJECT, gateway,
            prepared_environment=environment, reservation_identity=name)
        lifecycle = PostBehaviorCompositionFactory().build(request)
        lifecycle.reservation.current()  # Existing controlled Runtime; no HTTP/reservation is created.
        access = PostBehaviorStateRepository(root / "post-behavior").load_reservation(PROJECT)
        assert access.work_id == runtime_identity(name)
        assert lifecycle.reservation.binding.identity == name
        assert lifecycle.reservation.binding.storage_identity == PROJECT
        assert PostBehaviorStateRepository(root / "post-behavior").load(name) is None
        restored = PostBehaviorCompositionFactory().build(request)
        assert restored.reservation.binding.load().work_id == access.work_id
        work_ids.append(access.work_id)
        restored.stop()
    assert len(set(work_ids)) == 2
    assert len([call for call in runtime.calls if call["operation"] == "reserve"]) == 2
    assert git(canonical, "rev-parse", "main") == baseline
