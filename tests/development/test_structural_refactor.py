"""Real Python probes and Git revisions; model candidates are deterministic fakes."""
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from core.development.deterministic_regression import DeterministicRegressionService, SubprocessProjectRuntimeExecutor
from core.development.microcycle_domain import (
    BoundaryClassificationRequest, FragmentationRequest, FrontierExecutionRequest,
    FrontierMaterialisationRequest, LanguageAdapterCatalog, MicrocycleState,
    RegressionState, RetryCounts, ScenarioCompletion, ScenarioFrontier,
    ScenarioIntentResult, ScenarioParseRequest, TestScenarioDraft,
)
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.strict_microcycle import (
    GitFrontierMaterialiser, StrictMicrocycleDependencies, StrictMicrocycleRequest, StrictMicrocycleService,
)
from core.development.structural_refactor_domain import StructuralPhase
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult

PRODUCTION = """class RunningTotal:
    def __init__(self):
        self.total = 0

    def add(self, value):
        self.total += value

    def get(self):
        return self.total
"""
REPAIRED = PRODUCTION.replace("self.total", "self._total") + """
    def total(self):
        return self._total
"""
PRIOR = """from running_total import RunningTotal

def test_previous():
    rt = RunningTotal()
    rt.add(5)
    assert rt.get() == 5
"""
SCENARIO = """from running_total import RunningTotal

def test_current():
    rt = RunningTotal()
    rt.add(5)
    assert rt.total() == EXPECTED
"""


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


class DiskStore:
    def __init__(self, path):
        self.path = path

    def load(self, scenario_id):
        return MicrocycleState.from_dict(json.loads(self.path.read_text())) if self.path.exists() else None

    def save(self, state):
        self.path.write_text(json.dumps(state.to_dict()))


class CandidateGateway:
    def __init__(self, root, source=REPAIRED, edit_test=False):
        self.root = root
        self.source = source
        self.edit_test = edit_test
        self.calls = []

    async def execute(self, unit, binding):
        self.calls.append((unit, binding))
        if self.source is None:
            return WorkUnitExecutionResult(unit.id, False, "checks_failed", error="retained failure")
        worktree = self.root.parent / f"worker-{len(self.calls)}"
        git(self.root, "worktree", "add", "--detach", str(worktree), binding.base_sha)
        try:
            (worktree / "running_total.py").write_text(self.source)
            if self.edit_test:
                (worktree / "tests/test_previous.py").write_text("def test_previous(): pass\n")
            git(worktree, "add", ".")
            git(worktree, "commit", "--allow-empty", "-qm", "deterministic candidate")
            revision = git(worktree, "rev-parse", "HEAD")
        finally:
            git(self.root, "worktree", "remove", "--force", str(worktree))
        return WorkUnitExecutionResult(unit.id, True, "accepted", accepted_revision=revision,
                                       evidence_location=f"candidate-{len(self.calls)}")


def setup(tmp_path, expected=5, candidate=REPAIRED, edit_test=False):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Tests")
    git(root, "config", "user.email", "tests@example.test")
    (root / "tests").mkdir()
    (root / "running_total.py").write_text(PRODUCTION)
    (root / "tests/test_previous.py").write_text(PRIOR)
    source = SCENARIO.replace("EXPECTED", str(expected))
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("scenario", "SPEC_SENTINEL", "python", source,
                              "tests/test_current.py::test_current", "tests/test_current.py")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    index = len(fragments) - 1
    ids = tuple(item.fragment_id for item in fragments)
    frontier = ScenarioFrontier("scenario", index, ids[-1], ids)
    prefix = replace(frontier, index=index - 1, active_fragment_id=ids[-2], materialised_fragment_ids=ids[:-1])
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, prefix, "base"))
    (root / draft.test_path).write_text(artifact.complete_source)
    git(root, "add", ".")
    git(root, "commit", "-qm", "trusted accepted prefix")
    base = git(root, "rev-parse", "HEAD")
    state = MicrocycleState(draft, ScenarioIntentResult("scenario", "approved", "GATEKEEPER_SENTINEL"),
        model, fragments, frontier, base, None, RetryCounts(), (), (),
        RegressionState("pending", (sys.executable, "-m", "pytest", "-q")), ScenarioCompletion("pending"),
        candidate_chain_revision=base)
    store = DiskStore(tmp_path / "microcycle.json")
    store.save(state)
    gateway = CandidateGateway(root, candidate, edit_test)
    service = StrictMicrocycleService(StrictMicrocycleDependencies(
        store, GitFrontierMaterialiser(), gateway, LanguageAdapterCatalog((adapter,)),
        DeterministicRegressionService(SubprocessProjectRuntimeExecutor()),
    ))
    request = StrictMicrocycleRequest("project", "running_total.py", root,
        RepositoryBinding("project", "main", base, environment_resources=["HISTORY_SENTINEL"]),
        state, ("tests/test_previous.py::test_previous",))
    return service, request, gateway


async def steps(service, request, count):
    results = []
    for _ in range(count):
        results.append(await service.advance(request))
    return results


@pytest.mark.asyncio
async def test_exact_running_total_routes_structurally_and_minimizes_context(tmp_path):
    service, request, gateway = setup(tmp_path)
    observed, submitted = await steps(service, request, 2)
    assert observed.kind.value == "structural_refactor_required"
    problem = observed.state.boundary_evidence[-1].structural_problem
    assert problem.subject == "total"
    assert "non-callable data attribute" in problem.description
    assert "TypeError" in observed.state.boundary_evidence[-1].diagnostic.message
    unit, binding = gateway.calls[0]
    instruction, payload = unit.objective.split("\n", 1)
    assert instruction.startswith("You are the Structural Refactorer.")
    assert json.loads(payload) == {
        "production": [{"path": "running_total.py", "source": PRODUCTION}],
        "structural_problem": problem.description,
    }
    assert not any(word in unit.objective for word in ("SPEC_SENTINEL", "GATEKEEPER_SENTINEL", "HISTORY_SENTINEL", "assert"))
    assert binding.environment_resources == []
    assert unit.allowed_paths == ["running_total.py"]
    assert binding.base_sha == request.initial_state.development_base_revision
    assert submitted.state.development_base_revision == binding.base_sha
    assert submitted.state.structural_attempts[-1].phase == StructuralPhase.VALIDATING


@pytest.mark.asyncio
@pytest.mark.parametrize("expected,outcome,next_action", [(5, "green", "run_regression"), (6, "valid_behavioral_red", "submit_developer")])
async def test_repair_preserves_prior_tests_promotes_and_returns_to_normal_tdd(tmp_path, expected, outcome, next_action):
    service, request, gateway = setup(tmp_path, expected)
    results = await steps(service, request, 5)
    promoted = results[-1]
    assert promoted.kind.value == "structural_refactor_promoted"
    state = promoted.state
    assert state.structural_regression.status == "regression_clear"
    assert all(report.status == "passed" for report in state.structural_regression.reports)
    assert state.structural_rerun.outcome == outcome
    assert state.development_base_revision == state.structural_attempts[-1].candidate_revision
    assert state.development_base_revision != request.initial_state.development_base_revision
    assert state.boundary_evidence[0].outcome == "structural_refactor_required"
    assert state.structural_attempts[-1].phase == StructuralPhase.PROMOTED
    # New disk-backed service resumes without repeating the promoted model work.
    restarted = StrictMicrocycleService(StrictMicrocycleDependencies(
        DiskStore(service.state_store.path), GitFrontierMaterialiser(), gateway,
        service.adapters, service.regression,
    ))
    next_step = await restarted.advance(request)
    assert next_step.state.pending_action == next_action
    assert len(gateway.calls) == 1
    if outcome == "green":
        continuation = await steps(restarted, request, 3)
        assert continuation[-1].kind.value == "scenario_completed"
        assert continuation[-1].state.pending_action == "review_behavior"
    else:
        gateway.source = REPAIRED.replace("return self._total\n", "return self._total + 1\n")
        await restarted.advance(request)
        assert gateway.calls[-1][0].model_work_kind.value == "frontier_implementation"


@pytest.mark.asyncio
async def test_regression_failure_rejects_without_advancing_trust(tmp_path):
    service, request, gateway = setup(tmp_path, candidate=REPAIRED.replace("self._total += value", "self._total += 2 * value"))
    result = (await steps(service, request, 3))[-1]
    assert result.state.structural_regression.status == "accumulated_regression"
    assert result.state.structural_attempts[-1].phase == StructuralPhase.REJECTED
    assert result.state.development_base_revision == request.initial_state.development_base_revision
    assert git(request.repository_root, "rev-parse", "main") == request.initial_state.development_base_revision


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate,edit_test", [(REPAIRED, True), (REPAIRED + "\ndef unrelated(): return 9\n", False)])
async def test_tests_read_only_and_unrelated_changes_rejected_even_when_tests_pass(tmp_path, candidate, edit_test):
    service, request, gateway = setup(tmp_path, candidate=candidate, edit_test=edit_test)
    result = (await steps(service, request, 3))[-1]
    assert result.state.structural_attempts[-1].reason == "structural_candidate_outside_problem"
    assert result.state.development_base_revision == request.initial_state.development_base_revision


@pytest.mark.asyncio
async def test_exhaustion_is_bounded_and_preserves_all_attempts(tmp_path):
    service, request, gateway = setup(tmp_path, candidate=None)
    results = await steps(service, request, 6)
    assert results[-1].blocker_or_replan_reason == "structural_refactor_attempts_exhausted"
    assert len(gateway.calls) == 4
    assert len({unit.id for unit, _ in gateway.calls}) == 4
    assert len(results[-1].state.structural_attempts) == 4
    assert results[-1].state.development_base_revision == request.initial_state.development_base_revision


@pytest.mark.asyncio
async def test_interrupted_submission_is_never_resubmitted(tmp_path):
    service, request, gateway = setup(tmp_path)
    await service.advance(request)
    async def interrupt(unit, binding):
        assert service.state_store.load("scenario").structural_attempts[-1].phase == StructuralPhase.STARTED
        raise RuntimeError("simulated process death")
    gateway.execute = interrupt
    with pytest.raises(RuntimeError, match="process death"):
        await service.advance(request)
    restarted = StrictMicrocycleService(StrictMicrocycleDependencies(
        DiskStore(service.state_store.path), GitFrontierMaterialiser(), gateway, service.adapters, service.regression,
    ))
    result = await restarted.advance(request)
    assert result.blocker_or_replan_reason == "structural_refactor_interrupted_submission"
    assert result.state.development_base_revision == request.initial_state.development_base_revision


@pytest.mark.asyncio
async def test_generic_rack_envelope_has_no_stage_fields_or_context_resources(tmp_path):
    from core.execution.profiled_workspace_gateway import ProfiledWorkspaceExecutionGateway, ProfiledWorkspaceGatewayDependencies
    from core.development.athba_workspace_routing import AthbaExecutionProfileResolver
    from core.execution.workspace_execution_port import WorkspaceExecutionResult, WorkspaceExecutionStatus
    from core.execution.rack_ai_workspace_connector import RackAiV2WorkspaceSerializer
    service, request, gateway = setup(tmp_path)
    await steps(service, request, 2)
    unit, binding = gateway.calls[0]
    captured = []
    class Port:
        def submit_workspace_change(self, request):
            captured.append(request)
            return WorkspaceExecutionResult(request.identity, WorkspaceExecutionStatus.REJECTED)
    await ProfiledWorkspaceExecutionGateway(ProfiledWorkspaceGatewayDependencies(
        Port(), AthbaExecutionProfileResolver(),
    )).execute(unit, binding)
    wire = RackAiV2WorkspaceSerializer().serialize(captured[0])
    wire_text = json.dumps(wire)
    # The explicit role instruction belongs solely to the opaque objective.
    wire_text = wire_text.replace(json.dumps(unit.objective)[1:-1], "")
    assert "structural" not in wire_text.lower()
    assert "SPEC_SENTINEL" not in wire_text and "HISTORY_SENTINEL" not in wire_text
    assert captured[0].allowed_writable_paths == ("running_total.py",)


@pytest.mark.parametrize("body,production", [
    ("assert 1 + 'bad' == 1", PRODUCTION),
    ("value = 1\nvalue()", PRODUCTION),
    ("assert rt.total(unknown=1) == 5", PRODUCTION.replace("self.total = 0", "self.total = lambda: 1")),
    ("assert rt.boom() == 5", PRODUCTION + '\n    def boom(self):\n        raise TypeError("\'int\' object is not callable")\n'),
    ("assert rt.boom() == 5", PRODUCTION + "\n    def boom(self):\n        value = 1\n        return value()\n"),
    ("assert rt.total() == 5", PRODUCTION.replace("self.total = 0", "self._total = 0") + "\n    @property\n    def total(self):\n        return 0\n"),
    ("assert rt.total() == 5", PRODUCTION + "\n    def __getattribute__(self, name):\n        return object.__getattribute__(self, name)\n"),
    ("assert rt.total() == 5", PRODUCTION.replace("class RunningTotal:", "class RunningTotal(object):")),
])
def test_unrelated_runtime_errors_and_opaque_lookup_are_not_structural(tmp_path, body, production):
    (tmp_path / "running_total.py").write_text(production)
    source = "from running_total import RunningTotal\n\ndef test_current():\n    rt = RunningTotal()\n"
    source += "".join("    " + line + "\n" for line in body.splitlines())
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("scenario", "behavior", "python", source,
                             "test_current.py::test_current", "test_current.py")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    ids = tuple(item.fragment_id for item in fragments)
    frontier = ScenarioFrontier("scenario", len(ids) - 1, ids[-1], ids)
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, "base"))
    diagnostic = adapter.execute_frontier(FrontierExecutionRequest(artifact, str(tmp_path), draft.test_path, "running_total.py"))
    observed = adapter.classify_boundary(BoundaryClassificationRequest(diagnostic, artifact, fragments[-1], "green"))
    assert observed.outcome in {"unsupported_language_boundary", "failure_before_frontier"}
    assert observed.structural_problem is None


@pytest.mark.asyncio
async def test_persisted_validation_and_rerun_do_not_repeat_model_submission(tmp_path):
    service, request, gateway = setup(tmp_path)
    await steps(service, request, 2)
    for phase in (StructuralPhase.RERUN, StructuralPhase.PROMOTING, StructuralPhase.PROMOTED):
        service = StrictMicrocycleService(StrictMicrocycleDependencies(
            DiskStore(service.state_store.path), GitFrontierMaterialiser(), gateway, service.adapters, service.regression,
        ))
        result = await service.advance(request)
        assert result.state.structural_attempts[-1].phase == phase
        assert len(gateway.calls) == 1
        assert len(result.state.structural_attempts[-1].evidence_refs) >= 2


@pytest.mark.asyncio
async def test_unresolved_adapter_observation_rejects_and_stops_at_bound(tmp_path, monkeypatch):
    service, request, gateway = setup(tmp_path)
    original = await service.advance(request)
    assessment = original.state.boundary_evidence[-1]
    adapter = service.adapters.for_language("python")
    monkeypatch.setattr(adapter, "classify_boundary", lambda request: assessment)
    results = await steps(service, request, 13)
    assert results[-1].blocker_or_replan_reason == "structural_refactor_attempts_exhausted"
    assert len(gateway.calls) == 4
    assert all(item.phase == StructuralPhase.REJECTED for item in results[-1].state.structural_attempts)
    assert results[-1].state.development_base_revision == request.initial_state.development_base_revision
    assert all(item.reason == "structural_refactor_required" for item in results[-1].state.structural_attempts)


@pytest.mark.asyncio
async def test_changed_logic_inside_scope_rejected_despite_passing_old_tests(tmp_path):
    changed = REPAIRED.replace("return self._total\n", "return self._total + 0\n")
    service, request, gateway = setup(tmp_path, candidate=changed)
    result = (await steps(service, request, 3))[-1]
    assert result.state.structural_regression.status == "regression_clear"
    assert result.state.structural_attempts[-1].reason == "structural_candidate_outside_problem"


def test_missing_normalized_authority_is_invalid():
    from core.development.microcycle_domain import BoundaryAssessment, BoundaryDiagnostic
    with pytest.raises(ValueError, match="normalized problem"):
        BoundaryAssessment("structural_refactor_required", "frontier", BoundaryDiagnostic("runtime", "failure"))


@pytest.mark.asyncio
async def test_managed_revision_promotion_recovers_after_ref_update_before_state_save(tmp_path, monkeypatch):
    from core.development.microcycle_revision_git import MicrocycleGitClient
    from core.development.microcycle_revision_service import MicrocycleRevisionLifecycle, RevisionLifecycleDependencies
    from core.development.microcycle_revision_store import MicrocycleRevisionRepository
    from core.development.microcycle_revision_state import RevisionInitialisationRequest, RevisionBindingRequest, RevisionRecoveryRequest
    service, request, gateway = setup(tmp_path)
    lifecycle = MicrocycleRevisionLifecycle(RevisionLifecycleDependencies(
        MicrocycleRevisionRepository(tmp_path / "revisions"), MicrocycleGitClient(request.repository_root),
    ))
    lifecycle.initialise(RevisionInitialisationRequest(
        "scenario", "refs/heads/main", request.initial_state.development_base_revision,
    ))
    request = replace(request, revision_lifecycle=lifecycle,
                      revision_binding_request=RevisionBindingRequest("scenario", "project", str(request.repository_root)))
    await steps(service, request, 4)
    original_save = service.state_store.save
    def interrupted_save(state):
        if state.structural_attempts[-1].phase == StructuralPhase.PROMOTED:
            raise RuntimeError("after canonical promotion")
        original_save(state)
    monkeypatch.setattr(service.state_store, "save", interrupted_save)
    with pytest.raises(RuntimeError, match="canonical promotion"):
        await service.advance(request)
    persisted = service.state_store.load("scenario")
    candidate = persisted.structural_attempts[-1].candidate_revision
    assert persisted.structural_attempts[-1].phase == StructuralPhase.PROMOTING
    assert git(request.repository_root, "rev-parse", "main") == candidate
    monkeypatch.setattr(service.state_store, "save", original_save)
    recovered = await service.advance(request)
    assert recovered.state.development_base_revision == candidate
    assert lifecycle.recover(RevisionRecoveryRequest("scenario")).canonical_development_base == candidate
    assert len(gateway.calls) == 1
    next_step = await service.advance(request)
    assert next_step.state.pending_action == "run_regression"


def test_focused_production_omits_unrelated_class_members():
    from core.development.structural_refactor_domain import StructuralProblem, StructuralProductionSource
    source = PRODUCTION + "\n    def unrelated(self):\n        return 'UNRELATED_BEHAVIOR_SENTINEL'\n"
    problem = StructuralProblem("one collision", "running_total.py", 1, len(source.splitlines()), "total")
    focused = PythonPytestAdapter().focus_structural_production(StructuralProductionSource(problem, source))
    assert focused == PRODUCTION
    assert "UNRELATED_BEHAVIOR_SENTINEL" not in focused


@pytest.mark.parametrize("member,value", [("balance", "0"), ("entries", "[]"), ("label", "'data'")])
def test_runtime_recognition_is_not_running_total_or_exception_word_matching(tmp_path, member, value):
    source = f"class Subject:\n    def __init__(self):\n        self.{member} = {value}\n"
    (tmp_path / "subject.py").write_text(source)
    test = f"from subject import Subject\n\ndef test_subject():\n    obj = Subject()\n    obj.{member}()\n"
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("subject", "behavior", "python", test, "test_subject.py::test_subject", "test_subject.py")
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    ids = tuple(item.fragment_id for item in fragments)
    frontier = ScenarioFrontier("subject", len(ids) - 1, ids[-1], ids)
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, "base"))
    diagnostic = adapter.execute_frontier(FrontierExecutionRequest(artifact, str(tmp_path), draft.test_path, "subject.py"))
    result = adapter.classify_boundary(BoundaryClassificationRequest(diagnostic, artifact, fragments[-1], "green"))
    assert result.outcome == "structural_refactor_required"
    assert result.structural_problem.subject == member
