"""Real Git/regression/Gatekeeper composition with deterministic model boundaries."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.microcycle_domain import (
    BehaviorReviewState, FragmentationRequest, MicrocycleState, RegressionState, RetryCounts,
    ScenarioCompletion, ScenarioFrontier, ScenarioIntentResult, ScenarioParseRequest, TestScenarioDraft,
)
from core.development.post_behavior_composition import PostBehaviorCompositionFactory, PostBehaviorCompositionRequest
from core.development.post_behavior_domain import PostBehaviorOutcome, PostBehaviorStatus
from core.development.post_behavior_entry import AcceptedBehavioralDeliveryLoader
from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService, ProjectRuntime
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.specification_domain import (
    SourceRequirementClause, SpecificationChecklist, SpecificationChecklistItem, SpecificationGatekeeperRunState,
)
from core.development.strict_tdd_feature_domain import CompletedBehaviorReference, StrictTddFeatureState
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.workspace_execution_port import WorkspaceExecutionResult, WorkspaceExecutionStatus
from core.llm.contracts.provider import NormalizedResult, ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider

PROJECT = "counter-delivery"
NODE = "tests/test_counter.py::test_total"
SOURCE = """class LegacyCounter:
    def total(self, values):
        first = 0
        for value in values:
            first += value
        second = 0
        for value in values:
            second += value
        return first + second
"""
REFACTORED = """class SumCounter:
    def total(self, values):
        return sum(values) * 2
"""
TEST = """from counter import LegacyCounter


def test_total():
    counter = LegacyCounter()
    assert counter.total([1, 2, 3]) == 12
"""
REQUIREMENT = "For a list of integers, the total method returns twice their sum."


def git(root, *args):
    return subprocess.run(("git", *args), cwd=root, text=True, capture_output=True, check=True).stdout.strip()


def commit(root, message):
    git(root, "add", ".")
    git(root, "-c", "user.name=Deterministic Test", "-c", "user.email=test@example.invalid", "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


def seeded_delivery(tmp_path, consumer=False):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (root / "counter.py").write_text("")
    if consumer:
        (root / "consumer.py").write_text(
            "from counter import LegacyCounter\n\n"
            "def consume():\n    return LegacyCounter().total([1, 2, 3])\n\n"
            "def unrelated():\n    return 'UNRELATED_CONSUMER_SENTINEL'\n"
        )
    entry = commit(root, "trusted behavioral entry")
    (root / "counter.py").write_text(SOURCE)
    (root / "tests").mkdir()
    (root / "tests/test_counter.py").write_text(TEST)
    (root / "tests/test_prior.py").write_text("def test_prior():\n    assert 3 + 4 == 7\n")
    baseline = commit(root, "accepted behavioral implementation")
    state_root = tmp_path / "state"
    runtime = ProjectRuntime(
        "python", sys.version.split()[0], str(Path(sys.executable).parent),
        [sys.executable, "-m", "pytest", "-q", "-p", "no:django", "-p", "no:asyncio", "tests"],
    )
    project = DevelopmentProject(PROJECT, str(root), "main", baseline, runtime,
                                 ["counter.py", "tests/test_counter.py"], "ready")
    ProjectEnvironmentService(state_root / "projects").repo.save(project)
    clause = SourceRequirementClause("SRC-1", REQUIREMENT, "behavior")
    contract = BehaviorContract(
        "contract-1", PROJECT, "SumCounter", "total", REQUIREMENT,
        [clause], [BehaviorContractRequirement("B-1", ["SRC-1"], REQUIREMENT, "twice the sum", "test integers")],
        [], ["counter.py"], ["tests/test_counter.py"], public_api=["SumCounter.total(values)"],
        non_goals=["ARCHITECTURE_SENTINEL"],
    )
    keeper = SpecificationGatekeeperRunState(SpecificationChecklist(
        PROJECT, REQUIREMENT, [SpecificationChecklistItem("CHK-1", REQUIREMENT, "behavior")],
    ))
    feature = StrictTddFeatureState(
        PROJECT, "source-identity", "completed", contract_payload=contract.to_dict(),
        gatekeeper_payload=keeper.to_dict(),
        completed_behaviors=(CompletedBehaviorReference("B-1", "scenario-1", baseline, ("accepted",)),),
        canonical_ref="refs/heads/main", canonical_development_base=baseline,
        final_reconciliation=({"checklist_ref": "CHK-1", "answer": "YES", "rationale": "GATEKEEPER_SENTINEL"},),
        behavioral_entry_revision=entry,
    )
    StrictTddFeatureRepository(state_root / "features").save(feature)
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("scenario-1", "B-1", "python", TEST, NODE,
                              "tests/test_counter.py", source_requirement_refs=("SRC-1",))
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    frontier = ScenarioFrontier(draft.scenario_id, len(fragments) - 1, fragments[-1].fragment_id,
                                tuple(item.fragment_id for item in fragments))
    microcycle = MicrocycleState(
        draft, ScenarioIntentResult("scenario-1", "approved", "Accepted", ("evidence",)),
        model, fragments, frontier, baseline, None, RetryCounts(), (), (),
        RegressionState("regression_clear", tuple(runtime.test_command)),
        ScenarioCompletion("behavior_complete", baseline),
        behavior_review=BehaviorReviewState("approved", evidence_refs=("review",),
                                            reviewed_candidate_revision=baseline),
    )
    MicrocycleStateRepo(state_root / "microcycles").save(microcycle)
    return state_root, root, entry, baseline


class GenericGitExecution:
    def __init__(self, root, candidate_root):
        self.root = root
        self.candidate_root = candidate_root
        self.calls = []
        self.results = {}
        self.refactored_source = REFACTORED

    def submit_workspace_change(self, request):
        self.calls.append(request)
        path = self.candidate_root / f"candidate-{len(self.calls)}"
        git(self.root, "worktree", "add", "--detach", str(path), request.repository.base_sha)
        payload = json.loads(request.objective.split("\n", 1)[1])
        if "identifier_substitution" in payload:
            mapping = payload["identifier_substitution"]
            for relative in request.allowed_writable_paths:
                target = path / relative
                target.write_text(target.read_text().replace(mapping["current_name"], mapping["required_name"]))
        else:
            (path / "counter.py").write_text(self.refactored_source)
        revision = commit(path, "generic bounded candidate")
        result = WorkspaceExecutionResult(
            request.identity, WorkspaceExecutionStatus.ACCEPTED, candidate_revision=revision,
            accepted_revision=revision, changed_paths=request.allowed_writable_paths,
            execution_provenance={"worker_id": "deterministic-fake", "model_id": "deterministic-fake"},
            evidence_refs=(f"deterministic-execution:{revision}",),
        )
        self.results[request.identity.submission_id] = result
        return result

    def get_result(self, submission_id):
        return self.results.get(submission_id)

    def cancel(self, submission_id):
        return False


def configured_gateway(monkeypatch, responses):
    monkeypatch.setenv("OPENAI_API_KEY", "local-test-only")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:9999/v1")
    provider = OpenAIProvider(ProviderRetryPolicy(10, 0, 1))
    calls = []
    def invoke(request):
        calls.append(request)
        assert responses, f"unexpected provider call: {request.prompt}"
        return NormalizedResult(responses.pop(0), {}, {"provider": "local-deterministic-fake"})
    monkeypatch.setattr(provider, "invoke", invoke)
    return ProviderReasoningGateway(provider, "configured-local"), calls


def gatekeeper_yes():
    return json.dumps({"answer": "YES", "selected_test_names": [NODE], "rationale": "The supplied test proves the doubled sum."})


def evidence_records(state_root):
    return [json.loads(path.read_text()) for path in (state_root / "post-behavior" / PROJECT / "evidence").glob("*.json")]


@pytest.mark.asyncio
async def test_real_git_full_regression_existing_gatekeeper_and_restart_chain(tmp_path, monkeypatch):
    state_root, root, entry, baseline = seeded_delivery(tmp_path)
    responses = [
        "LegacyCounter -> SumCounter", gatekeeper_yes(), "NO",
        "YES\nobjective: Replace duplicated accumulation with one sum calculation.\nreason: Removes an identical loop.",
        gatekeeper_yes(), "NO",
    ]
    gateway, calls = configured_gateway(monkeypatch, responses)
    execution = GenericGitExecution(root, tmp_path)
    composition = PostBehaviorCompositionRequest(state_root, PROJECT, gateway, execution)
    statuses = []
    # Reconstruct production composition after every legal durable transition.
    for _ in range(30):
        lifecycle = PostBehaviorCompositionFactory().build(composition)
        state = await lifecycle.advance(PROJECT)
        statuses.append(state.status)
        if state.terminal:
            break
    assert state.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE, state.diagnostic
    assert not responses
    assert len(calls) == 6
    assert len(execution.calls) == 2
    promoted = [item for item in state.passes if item.outcome == PostBehaviorOutcome.PROMOTED]
    assert len(promoted) == 2
    renamed, refactored = [item.candidate.revision for item in promoted]
    assert len({entry, baseline, renamed, refactored}) == 4
    assert state.behaviorally_accepted_revision == baseline
    assert state.current_post_behavior_revision == git(root, "rev-parse", "main") == refactored
    assert ProjectEnvironmentService(state_root / "projects").repo.load(PROJECT).trusted_base_sha == refactored
    assert [request.repository.base_sha for request in execution.calls] == [baseline, renamed]
    assert git(root, "show", f"{baseline}:tests/test_counter.py") == TEST.strip()
    assert git(root, "show", f"{renamed}:tests/test_counter.py") == TEST.replace("LegacyCounter", "SumCounter").strip()
    assert git(root, "diff", renamed, refactored, "--", "tests") == ""
    assert git(root, "status", "--porcelain") == ""
    assert execution.calls[0].allowed_writable_paths == ("counter.py", "tests/test_counter.py")
    assert execution.calls[1].allowed_writable_paths == ("counter.py",)
    for item in promoted:
        assert item.tests.passed and item.gatekeeper.passed
        assert item.tests.revision == item.gatekeeper.revision == item.candidate.revision
        assert item.reconciliation_progress
    records = evidence_records(state_root)
    regression = [item["payload"] for item in records if item["kind"] == "accepted_regression"]
    assert len(regression) == 2
    assert all("2 passed" in item["report"]["evidence_ref"] for item in regression)
    assert {item["revision"] for item in regression} == {renamed, refactored}
    provider_records = [item["payload"] for item in records if item["kind"] == "local_reasoning"]
    assert len(provider_records) == 12
    assert sum(item["completed"] for item in provider_records) == 6
    results = [item["payload"] for item in records if item["kind"] == "workspace_result"]
    assert len(results) == 2
    assert all(item["execution_provenance"]["worker_id"] == "deterministic-fake" for item in results)
    assessor_prompts = [calls[index].prompt for index in (0, 2, 3, 5)]
    assert all("SENTINEL" not in prompt and "test_prior" not in prompt for prompt in assessor_prompts)
    assert "LegacyCounter" in calls[0].prompt
    assert "LegacyCounter" not in calls[2].prompt
    assert "sum(values) * 2" in calls[5].prompt
    # Existing reconciliation sees the exact accepted renamed test, with its original authority retained locally.
    assert "assert counter.total([1, 2, 3]) == 12" in calls[1].prompt
    assert "def test_total" in calls[4].prompt
    restarted = PostBehaviorCompositionFactory().build(composition)
    assert await restarted.run(PROJECT) == state
    assert len(calls) == 6 and len(execution.calls) == 2


@pytest.mark.asyncio
async def test_real_composition_no_work_keeps_original_baseline(tmp_path, monkeypatch):
    state_root, root, _, baseline = seeded_delivery(tmp_path)
    gateway, calls = configured_gateway(monkeypatch, ["NO", "NO"])
    execution = GenericGitExecution(root, tmp_path)
    lifecycle = PostBehaviorCompositionFactory().build(PostBehaviorCompositionRequest(state_root, PROJECT, gateway, execution))
    state = await lifecycle.run(PROJECT)
    assert state.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE, state.diagnostic
    assert state.current_post_behavior_revision == state.behaviorally_accepted_revision == baseline
    assert git(root, "rev-parse", "main") == baseline
    assert len(calls) == 2 and execution.calls == []


def test_entry_loader_rejects_unapproved_or_missing_baseline_authority(tmp_path):
    state_root, _, _, _ = seeded_delivery(tmp_path)
    repository = StrictTddFeatureRepository(state_root / "features")
    feature = repository.load(PROJECT)
    repository.save(replace(feature, final_reconciliation=({"checklist_ref": "CHK-1", "answer": "NO"},)))
    with pytest.raises(ValueError, match="final Specification Gatekeeper"):
        AcceptedBehavioralDeliveryLoader(state_root).load(PROJECT)
    repository.save(replace(feature, behavioral_entry_revision=None))
    with pytest.raises(ValueError, match="entry revision"):
        AcceptedBehavioralDeliveryLoader(state_root).load(PROJECT)



@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["tests", "gatekeeper"])
async def test_real_candidate_validation_failure_retains_last_accepted_revision(tmp_path, monkeypatch, failure):
    state_root, root, _, baseline = seeded_delivery(tmp_path)
    responses = [
        "LegacyCounter -> SumCounter", gatekeeper_yes(), "NO",
        "YES\nobjective: Replace duplicated accumulation with one sum calculation.\nreason: Removes an identical loop.",
    ]
    if failure == "gatekeeper":
        responses.extend([
            json.dumps({"answer": "NO", "selected_test_names": [], "rationale": "Evidence is insufficient."}),
            json.dumps({"disposition": "unsplittable", "rationale": "The requirement is already atomic."}),
        ])
    gateway, calls = configured_gateway(monkeypatch, responses)
    execution = GenericGitExecution(root, tmp_path)
    if failure == "tests":
        execution.refactored_source = REFACTORED.replace("sum(values) * 2", "0")
    lifecycle = PostBehaviorCompositionFactory().build(PostBehaviorCompositionRequest(
        state_root, PROJECT, gateway, execution,
    ))
    state = await lifecycle.run(PROJECT)
    assert state.status == PostBehaviorStatus.BLOCKED
    renamed = state.passes[0].candidate.revision
    rejected = state.passes[-1]
    assert state.behaviorally_accepted_revision == baseline
    assert state.current_post_behavior_revision == git(root, "rev-parse", "main") == renamed
    assert rejected.outcome == PostBehaviorOutcome.REJECTED
    assert rejected.candidate.revision != renamed
    assert rejected.tests.passed == (failure == "gatekeeper")
    if failure == "tests":
        assert rejected.gatekeeper is None
        assert len(calls) == 4
    else:
        assert not rejected.gatekeeper.passed
        assert rejected.reconciliation_progress
        assert len(calls) == 6
    assert len(execution.calls) == 2
    assert not responses
    assert git(root, "diff", baseline, renamed, "--", "tests/test_prior.py") == ""



@pytest.mark.asyncio
@pytest.mark.parametrize("staged", [False, True])
async def test_independent_workspace_changes_prevent_promotion_without_discard(tmp_path, monkeypatch, staged):
    state_root, root, _, baseline = seeded_delivery(tmp_path)
    gateway, calls = configured_gateway(monkeypatch, ["LegacyCounter -> SumCounter", gatekeeper_yes()])
    execution = GenericGitExecution(root, tmp_path)
    lifecycle = PostBehaviorCompositionFactory().build(PostBehaviorCompositionRequest(
        state_root, PROJECT, gateway, execution,
    ))
    for _ in range(10):
        state = await lifecycle.advance(PROJECT)
        if state.active_pass and state.active_pass.gatekeeper:
            break
    assert state.active_pass.tests.passed and state.active_pass.gatekeeper.passed
    wip = SOURCE + "\n# independent user work must survive\n"
    (root / "counter.py").write_text(wip)
    if staged:
        git(root, "add", "counter.py")
    with pytest.raises(ValueError, match="independent project worktree edits"):
        await lifecycle.advance(PROJECT)
    assert (root / "counter.py").read_text() == wip
    assert git(root, "rev-parse", "main") == baseline
    persisted = lifecycle.repository.load(PROJECT)
    assert persisted.current_post_behavior_revision == baseline
    assert len(execution.calls) == 1 and len(calls) == 2



@pytest.mark.asyncio
async def test_unchanged_production_consumer_renames_through_generic_execution(tmp_path, monkeypatch):
    state_root, root, _, baseline = seeded_delivery(tmp_path, consumer=True)
    gateway, calls = configured_gateway(monkeypatch, [
        "LegacyCounter -> SumCounter", gatekeeper_yes(), "NO", "NO",
    ])
    execution = GenericGitExecution(root, tmp_path)
    lifecycle = PostBehaviorCompositionFactory().build(PostBehaviorCompositionRequest(
        state_root, PROJECT, gateway, execution,
    ))
    state = await lifecycle.run(PROJECT)
    assert state.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE, state.diagnostic
    assert len(execution.calls) == 1
    request = execution.calls[0]
    assert set(request.allowed_writable_paths) == {"counter.py", "consumer.py", "tests/test_counter.py"}
    assert "UNRELATED_CONSUMER_SENTINEL" not in request.objective
    assert "consumer.py" not in calls[0].prompt
    assert "consumer.py" not in calls[2].prompt
    assert "consumer.py" not in calls[3].prompt
    assert state.passes[0].candidate.model_originated
    original = git(root, "show", f"{baseline}:consumer.py")
    assert git(root, "show", f"{state.current_post_behavior_revision}:consumer.py") == original.replace("LegacyCounter", "SumCounter")
