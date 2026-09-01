import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from core.development.deterministic_regression import DeterministicRegressionService
from core.development.microcycle_domain import (
    BoundaryOutcome,
    FrontierMaterialisationRequest,
    MicrocycleState,
    RegressionState,
    ScenarioCompletion,
    ScenarioFrontier,
    ScenarioIntentResult,
    ScenarioModel,
    TestScenarioDraft,
)
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.strict_tdd_transitions import MicrocycleTransitionKind
from core.development.strict_microcycle import (
    FrontierCandidate,
    RegressionRepairContext,
    GitFrontierMaterialiser,
    StrictMicrocycleDependencies,
    StrictMicrocycleRequest,
    StrictMicrocycleService,
)
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult


SOURCE = """from widget import Widget

def test_widget():
    widget = Widget()
    widget.grow()
    assert widget.count == 1
"""


class MemoryStore:
    def __init__(self):
        self.values = {}
        self.history = []

    def load(self, scenario_id):
        return self.values.get(scenario_id)

    def save(self, state):
        self.values[state.scenario_draft.scenario_id] = state
        self.history.append(state)


class CandidateRepository:
    def __init__(self, root, production):
        self.root = root
        self.production = production
        self.calls = []
        self.cleaned = []

    def materialise(self, request):
        number = len(self.calls)
        worktree = self.root / f"candidate-{number}"
        worktree.mkdir()
        base = request.artifact.base_revision
        source = self.production[base] if base in self.production else self.production["method" if "method" in base else "type"]
        (worktree / "widget.py").write_text(source)
        target = worktree / request.test_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(request.artifact.complete_source)
        revision = f"frontier-{number}-{request.artifact.base_revision}"
        self.calls.append(request)
        return FrontierCandidate(replace(request.artifact, candidate_revision=revision), revision, worktree, self.root)

    def cleanup(self, candidate):
        self.cleaned.append(candidate.candidate_revision)


class PassingRuntime:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return __import__("core.development.microcycle_domain", fromlist=["RegressionCommandReport"]).RegressionCommandReport(
            request.target, request.command, 0, "passed", f"evidence/{request.target}"
        )


def regression():
    return DeterministicRegressionService(PassingRuntime())


class Gateway:
    def __init__(self, revisions):
        self.revisions = list(revisions)
        self.units = []

    async def execute(self, unit, binding):
        self.units.append((unit, binding))
        revision = self.revisions.pop(0)
        return WorkUnitExecutionResult(
            unit.id,
            accepted=revision is not None,
            status="checks_passed" if revision else "checks_failed",
            accepted_revision=revision,
            evidence_location=f"evidence/{unit.id}",
            error=None if revision else "active frontier still fails",
        )


def initial_state():
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft(
        "generic-scenario", "generic-behavior", "python", SOURCE,
        "tests/test_widget.py::test_widget", "tests/test_widget.py",
    )
    model = adapter.parse_scenario(type("Request", (), {"draft": draft})())
    fragments = adapter.fragment_scenario(type("Request", (), {"model": model})())
    frontier = ScenarioFrontier(draft.scenario_id, 0, fragments[0].fragment_id, (fragments[0].fragment_id,))
    return MicrocycleState(
        draft,
        ScenarioIntentResult(draft.scenario_id, "approved", "approved", ("SRC-1",)),
        model,
        fragments,
        frontier,
        "base",
        None,
        __import__("core.development.microcycle_domain", fromlist=["RetryCounts"]).RetryCounts(),
        (),
        (),
        RegressionState("pending", ("pytest", "-q")),
        ScenarioCompletion("pending"),
    )


def request(tmp_path, state):
    return StrictMicrocycleRequest(
        "generic-project",
        "widget.py",
        tmp_path,
        RepositoryBinding("generic-project", "main", "base"),
        state,
    )


@pytest.mark.asyncio
async def test_generic_microcycle_exposes_one_frontier_at_a_time_and_persists_red_green(tmp_path):
    store = MemoryStore()
    candidates = CandidateRepository(
        tmp_path,
        {
            "base": "",
            "type": "class Widget:\n    def __init__(self):\n        self.count = 0\n",
            "frontier-1-type": "class Widget:\n    def __init__(self):\n        self.count = 0\n",
            "frontier-2-type": "class Widget:\n    def __init__(self):\n        self.count = 0\n",
            "method": "class Widget:\n    def __init__(self):\n        self.count = 0\n\n    def grow(self):\n        pass\n",
            "frontier-4-method": "class Widget:\n    def __init__(self):\n        self.count = 0\n\n    def grow(self):\n        pass\n",
            "green": "class Widget:\n    def __init__(self):\n        self.count = 0\n\n    def grow(self):\n        self.count += 1\n",
        },
    )
    gateway = Gateway(["type", "method", "green"])
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(store, candidates, gateway, type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(), regression())
    )

    outcome = await service.run(request(tmp_path, initial_state()))

    assert outcome.status == "scenario_complete"
    observed_indices = [item.artifact.frontier_index for item in candidates.calls]
    assert observed_indices[0] == 0
    assert set(observed_indices) == {0, 1, 2, 3}
    assert {item.artifact.canonical_test_identity for item in candidates.calls} == {"tests/test_widget.py::test_widget"}
    expected_fragments = initial_state().fragments
    assert all(item.artifact.active_fragment_id == expected_fragments[item.artifact.frontier_index].fragment_id for item in candidates.calls)
    assert gateway.units
    assert "Widget()" not in gateway.units[0][0].objective
    assert "assert widget.count" not in gateway.units[0][0].objective
    assert all(item.allowed_paths == ["widget.py"] for item, _binding in gateway.units)
    assert all(item.acceptance.commands[0][-1] == "tests/test_widget.py::test_widget" for item, _binding in gateway.units)
    outcomes = [item.outcome for item in outcome.state.boundary_evidence]
    assert outcomes == [
        BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value,
        BoundaryOutcome.GREEN.value,
        BoundaryOutcome.GREEN.value,
        BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value,
        BoundaryOutcome.GREEN.value,
        BoundaryOutcome.VALID_BEHAVIORAL_RED.value,
        BoundaryOutcome.GREEN.value,
    ]
    assert outcome.state.completion.completed_revision == outcome.state.development_base_revision
    assert len(outcome.state.developer_attempts) == 3
    assert any(item.current_accepted_red_revision is not None for item in store.history)
    assert any(item.developer_attempts for item in store.history)
    assert len(candidates.cleaned) == len(candidates.calls)


@pytest.mark.asyncio
async def test_invalid_syntax_never_reaches_developer(tmp_path):
    class InvalidAdapter(PythonPytestAdapter):
        def materialise_frontier(self, value):
            artifact = super().materialise_frontier(value)
            return replace(artifact, complete_source="def test_broken(:\n")

    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"base": ""})
    gateway = Gateway([])
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(store, candidates, gateway, type("Catalog", (), {"for_language": lambda self, _language: InvalidAdapter()})(), regression())
    )

    outcome = await service.run(request(tmp_path, initial_state()))

    assert outcome.status == BoundaryOutcome.INVALID_TEST_SYNTAX.value
    assert gateway.units == []
    assert outcome.state.boundary_evidence[-1].outcome == BoundaryOutcome.INVALID_TEST_SYNTAX.value


@pytest.mark.asyncio
async def test_developer_attempt_cap_is_durable_across_restarts(tmp_path):
    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"base": ""})
    gateway = Gateway([None, None, None, None])
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(store, candidates, gateway, type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(), regression())
    )
    value = request(tmp_path, initial_state())

    for _ in range(4):
        outcome = await service.run(value)
        assert outcome.status == "developer_candidate_rejected"
    exhausted = await service.run(value)

    assert exhausted.status == "developer_attempts_exhausted"
    assert len(gateway.units) == 4
    assert exhausted.state.frontier_attempt_counts[-1].developer_attempts == 4


def test_git_materialiser_commits_only_the_complete_authorised_test_artifact(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run(root, "init", "-q")
    run(root, "config", "user.name", "test")
    run(root, "config", "user.email", "test@example.test")
    (root / "widget.py").write_text("VALUE = 1\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_widget.py").write_text("def test_widget():\n    assert False\n")
    run(root, "add", ".")
    run(root, "commit", "-qm", "base")
    base = run(root, "rev-parse", "HEAD").strip()
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("git-scenario", "behavior", "python", "def test_widget():\n    assert True\n", "tests/test_widget.py::test_widget", "tests/test_widget.py")
    model = adapter.parse_scenario(type("Request", (), {"draft": draft})())
    fragments = adapter.fragment_scenario(type("Request", (), {"model": model})())
    frontier = ScenarioFrontier("git-scenario", 0, fragments[0].fragment_id, (fragments[0].fragment_id,))
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, base))
    materialiser = GitFrontierMaterialiser()

    candidate = materialiser.materialise(type("Request", (), {"artifact": artifact, "repository_root": root, "test_path": "tests/test_widget.py"})())

    assert run(root, "rev-parse", "HEAD").strip() == base
    assert run(root, "diff", "--name-only", base, candidate.candidate_revision).splitlines() == ["tests/test_widget.py"]
    assert run(root, "show", f"{candidate.candidate_revision}:tests/test_widget.py") == artifact.complete_source
    materialiser.cleanup(candidate)
    assert not candidate.project_root.exists()


def run(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout

@pytest.mark.asyncio
async def test_regression_repair_is_bounded_to_new_failures_and_reruns_full_suite(tmp_path):
    from core.development.deterministic_regression import ACCUMULATED_REGRESSION
    from core.development.microcycle_domain import BoundaryAssessment, BoundaryDiagnostic, RegressionState

    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"type": "class Widget:\n    def __init__(self):\n        self.count = 0\n"})
    gateway = Gateway(["repair"])
    runtime = PassingRuntime()
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            gateway,
            type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(),
            DeterministicRegressionService(runtime),
        )
    )
    state = initial_state()
    assessment = BoundaryAssessment(
        BoundaryOutcome.GREEN.value,
        state.frontier.active_fragment_id,
        BoundaryDiagnostic("green", "passed"),
    )
    state = replace(
        state,
        candidate_chain_revision="type",
        boundary_evidence=(assessment,),
        regression=RegressionState(
            ACCUMULATED_REGRESSION,
            ("pytest", "-q"),
            failing_prior_test_nodes=("tests/test_prior.py::test_prior",),
        ),
    )
    repaired, outcome = await service.repair_service.repair(
        RegressionRepairContext(request(tmp_path, state), state, PythonPytestAdapter())
    )

    assert outcome.status == "green"
    assert repaired.retry_counts.regression == 1
    assert "tests/test_prior.py::test_prior" in gateway.units[0][0].objective
    assert [item.target for item in runtime.requests] == [
        "tests/test_widget.py::test_widget",
        "accepted_regression_suite",
    ]

@pytest.mark.asyncio
async def test_development_base_does_not_advance_until_deterministic_regression_is_clear(tmp_path):
    from core.development.microcycle_domain import RegressionCommandReport

    class FailingSuiteRuntime:
        def execute(self, request):
            status = "failed" if request.target == "accepted_regression_suite" else "passed"
            return RegressionCommandReport(request.target, request.command, 1 if status == "failed" else 0, status, request.target)

    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"base": "", "type": "class Widget:\n    def __init__(self):\n        self.count = 0\n"})
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            Gateway(["type"]),
            type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(),
            DeterministicRegressionService(FailingSuiteRuntime()),
        )
    )

    outcome = await service.run(request(tmp_path, initial_state()))

    assert outcome.status == "accumulated_regression"
    assert outcome.state.development_base_revision == "base"


class SequencedReviewer:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    async def review(self, request):
        self.requests.append(request)
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_completed_behavior_repair_is_regressed_then_reviewed_again_before_completion(tmp_path):
    from core.development.behavior_completion import (
        APPROVED,
        REPAIR_REQUIRED,
        BehaviorCompletionDependencies,
        BehaviorCompletionService,
        BehaviorReviewResult,
    )
    from core.development.behavior_repair import BehaviorRepairDependencies, BehaviorRepairService

    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"repair": "class Widget:\n    pass\n"})
    gateway = Gateway(["repair"])
    reviewer = SequencedReviewer([
        BehaviorReviewResult(REPAIR_REQUIRED, "semantic gap", ("review/1",), ("durable update is missing",)),
        BehaviorReviewResult(APPROVED, "repair resolves the gap", ("review/2",)),
    ])
    completion = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer))
    repair = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, regression())
    )
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            gateway,
            type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(),
            regression(),
            behavior_completion=completion,
            behavior_repair=repair,
        )
    )
    state = replace(
        initial_state(),
        completion=ScenarioCompletion("scenario_complete", "base"),
        regression=RegressionState("regression_clear", ("pytest", "-q")),
    )

    outcome = await service.run(request(tmp_path, state))

    assert outcome.status == "behavior_complete"
    assert len(reviewer.requests) == 2
    assert len(gateway.units) == 1
    assert outcome.state.behavior_review.repair.attempts == 1
    assert outcome.state.behavior_review.verdict == APPROVED


@pytest.mark.asyncio
async def test_replan_is_durable_and_never_submits_a_developer_repair(tmp_path):
    from core.development.behavior_completion import (
        REPLAN_REQUIRED,
        BehaviorCompletionDependencies,
        BehaviorCompletionService,
        BehaviorReviewResult,
    )
    from core.development.behavior_repair import BehaviorRepairDependencies, BehaviorRepairService

    store = MemoryStore()
    candidates = CandidateRepository(tmp_path, {"base": ""})
    gateway = Gateway([])
    reviewer = SequencedReviewer([
        BehaviorReviewResult(
            REPLAN_REQUIRED,
            "the plan has no observable acceptance boundary",
            ("review/replan",),
            ("a higher-level behavior split is required",),
        )
    ])
    completion = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer))
    repair = BehaviorRepairService(
        BehaviorRepairDependencies(store, candidates, gateway, regression())
    )
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            gateway,
            type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(),
            regression(),
            behavior_completion=completion,
            behavior_repair=repair,
        )
    )
    state = replace(
        initial_state(),
        completion=ScenarioCompletion("scenario_complete", "base"),
        regression=RegressionState("regression_clear", ("pytest", "-q")),
    )

    first = await service.run(request(tmp_path, state))
    resumed = await service.run(request(tmp_path, state))

    assert first.status == resumed.status == REPLAN_REQUIRED
    assert first.state.behavior_review.replan is not None
    assert first.state.completion.status == "scenario_complete"
    assert gateway.units == []
    assert len(reviewer.requests) == 1


@pytest.mark.asyncio
async def test_manual_advances_isolate_normal_microcycle_effects(tmp_path):
    store = MemoryStore()
    candidates = CandidateRepository(
        tmp_path,
        {
            "base": "",
            "type": "class Widget:\n    def __init__(self):\n        self.count = 0\n",
            "frontier-1-type": "class Widget:\n    def __init__(self):\n        self.count = 0\n",
            "frontier-2-type": "class Widget:\n    def __init__(self):\n        self.count = 0\n",
            "method": "class Widget:\n    def __init__(self):\n        self.count = 0\n\n    def grow(self):\n        pass\n",
            "frontier-4-method": "class Widget:\n    def __init__(self):\n        self.count = 0\n\n    def grow(self):\n        pass\n",
            "green": "class Widget:\n    def __init__(self):\n        self.count = 0\n\n    def grow(self):\n        self.count += 1\n",
        },
    )
    runtime = PassingRuntime()
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            Gateway(["type", "method", "green"]),
            type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(),
            DeterministicRegressionService(runtime),
        )
    )
    results = []
    value = request(tmp_path, initial_state())

    for _ in range(60):
        advanced = await service.advance(value)
        results.append(advanced)
        if advanced.kind == MicrocycleTransitionKind.SCENARIO_COMPLETED:
            break

    assert results[-1].kind == MicrocycleTransitionKind.SCENARIO_COMPLETED
    assert all(not (item.rack_ai_invoked and item.deterministic_regression_invoked) for item in results)
    assert all(not (item.external_reasoning_invoked and item.rack_ai_invoked) for item in results)
    developer = next(item for item in results if item.kind == MicrocycleTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED)
    green = next(item for item in results if item.kind == MicrocycleTransitionKind.GREEN_VERIFIED)
    regression_result = next(item for item in results if item.kind == MicrocycleTransitionKind.REGRESSION_CLEAR)
    promotion = next(item for item in results if item.kind == MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED)
    frontier = next(item for item in results if item.kind == MicrocycleTransitionKind.FRONTIER_ADVANCED)
    assert developer.rack_ai_invoked and not developer.deterministic_regression_invoked
    assert not green.rack_ai_invoked and not green.deterministic_regression_invoked
    assert regression_result.deterministic_regression_invoked and not regression_result.rack_ai_invoked
    assert not promotion.deterministic_regression_invoked and not promotion.rack_ai_invoked
    assert not frontier.deterministic_regression_invoked and not frontier.rack_ai_invoked
    assert runtime.requests


@pytest.mark.asyncio
async def test_regression_repair_submission_regression_and_promotion_are_isolated(tmp_path):
    from core.development.deterministic_regression import ACCUMULATED_REGRESSION
    from core.development.microcycle_domain import BoundaryAssessment, BoundaryDiagnostic

    store = MemoryStore()
    candidates = CandidateRepository(
        tmp_path,
        {"type": "class Widget:\n    def __init__(self):\n        self.count = 0\n"},
    )
    gateway = Gateway(["repair"])
    runtime = PassingRuntime()
    service = StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            gateway,
            type("Catalog", (), {"for_language": lambda self, _language: PythonPytestAdapter()})(),
            DeterministicRegressionService(runtime),
        )
    )
    state = replace(
        initial_state(),
        candidate_chain_revision="type",
        boundary_evidence=(
            BoundaryAssessment(
                BoundaryOutcome.GREEN.value,
                initial_state().frontier.active_fragment_id,
                BoundaryDiagnostic("green", "passed"),
            ),
        ),
        regression=RegressionState(
            ACCUMULATED_REGRESSION,
            ("pytest", "-q"),
            failing_prior_test_nodes=("tests/test_prior.py::test_prior",),
        ),
    )
    context = RegressionRepairContext(request(tmp_path, state), state, PythonPytestAdapter())

    submitted, submission = await service.repair_service.submit(context)

    assert submission.status == "regression_repair_submitted"
    assert len(gateway.units) == 1
    assert runtime.requests == []

    regressed, verification = service.repair_service.run_regression(
        RegressionRepairContext(request(tmp_path, submitted), submitted, PythonPytestAdapter())
    )

    assert verification.status == "green"
    assert len(gateway.units) == 1
    assert runtime.requests
    runtime_count = len(runtime.requests)

    promoted = service.repair_service.promote(request(tmp_path, regressed), regressed)

    assert promoted.development_base_revision == regressed.candidate_chain_revision
    assert len(gateway.units) == 1
    assert len(runtime.requests) == runtime_count
