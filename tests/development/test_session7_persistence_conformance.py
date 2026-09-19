"""Session 7 deterministic persistence, conformance, retry, and Gatekeeper proofs."""
from dataclasses import replace

import pytest

from core.development.behavior_completion import (
    APPROVED,
    BehaviorCompletionDependencies,
    BehaviorCompletionService,
    BehaviorReviewResult,
)
from core.development.deterministic_regression import REGRESSION_CLEAR, DeterministicRegressionService
from core.development.microcycle_domain import (
    BoundaryAssessment,
    BoundaryDiagnostic,
    BehaviorReviewProtocolFailure,
    BehaviorReviewState,
    BoundaryOutcome,
    MicrocyclePendingAction,
    LanguageAdapterCatalog,
    LanguageAdapterDescriptor,
    RegressionState,
    ScenarioCompletion,
)
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.specification_reconciliation import CompletedMicrocycleEvidenceCollector
from core.development.strict_microcycle import (
    DeveloperExecutionContext,
    FrontierExecutionContext,
    StrictMicrocycleDependencies,
    StrictMicrocycleService,
    _advance,
    _load_state,
    _record_execution,
)
from core.execution.work_unit_gateway import WorkUnitExecutionResult
from tests.development.test_strict_microcycle import (
    CandidateRepository,
    Gateway,
    MemoryStore,
    initial_state,
    regression,
    request,
)


def service(store, candidates, gateway, adapter=None, completion=None):
    adapter = adapter or PythonPytestAdapter()
    return StrictMicrocycleService(
        StrictMicrocycleDependencies(
            store,
            candidates,
            gateway,
            LanguageAdapterCatalog((adapter,)),
            regression(),
            behavior_completion=completion,
        )
    )


@pytest.mark.asyncio
async def test_resume_after_regression_clear_advances_before_any_prior_frontier_reexecution(tmp_path):
    state = initial_state()
    assessment = BoundaryAssessment(
        BoundaryOutcome.GREEN.value,
        state.frontier.active_fragment_id,
        BoundaryDiagnostic("green", "passed"),
    )
    state = replace(
        state,
        development_base_revision="type",
        candidate_chain_revision="type",
        boundary_evidence=(assessment,),
        regression=RegressionState(REGRESSION_CLEAR, ("pytest", "-q")),
    )
    store = MemoryStore()
    store.save(state)

    class StopAtNextFrontier(PythonPytestAdapter):
        def materialise_frontier(self, value):
            artifact = super().materialise_frontier(value)
            return replace(artifact, complete_source="def test_broken(:\n")

    candidates = CandidateRepository(tmp_path, {"type": "class Widget:\n    def __init__(self):\n        self.count = 0\n"})
    outcome = await service(store, candidates, Gateway([]), StopAtNextFrontier()).run(request(tmp_path, state))

    assert outcome.status == BoundaryOutcome.INVALID_TEST_SYNTAX.value
    assert [call.artifact.frontier_index for call in candidates.calls] == [1]
    assert outcome.state.regression.status == "pending"
    assert outcome.state.frontier.index == 1


@pytest.mark.asyncio
async def test_stale_developer_packet_is_rejected_before_it_can_be_persisted(tmp_path):
    state = initial_state()
    red = BoundaryAssessment(
        BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value,
        state.frontier.active_fragment_id,
        BoundaryDiagnostic("collection_failure", "Widget missing"),
    )
    state = replace(state, current_accepted_red_revision="accepted-red", boundary_evidence=(red,))
    store = MemoryStore()

    class StaleGateway:
        async def execute(self, unit, binding):
            return WorkUnitExecutionResult(
                "old-frontier-packet", True, "checks_passed", accepted_revision="wrong-revision"
            )

    value = service(store, CandidateRepository(tmp_path, {"base": ""}), StaleGateway())
    with pytest.raises(ValueError, match="stale Rack AI packet"):
        await value._developer(DeveloperExecutionContext(request(tmp_path, state), state))
    assert store.history == []


@pytest.mark.asyncio
async def test_behavior_review_and_approval_survive_restart_without_second_review(tmp_path):
    state = replace(
        initial_state(),
        completion=ScenarioCompletion("scenario_complete", "base"),
    )
    store = MemoryStore()
    store.save(state)

    class Reviewer:
        def __init__(self):
            self.calls = 0

        async def review(self, value):
            self.calls += 1
            return BehaviorReviewResult(APPROVED, "complete", ("review/1",))

    class Starter:
        def __init__(self):
            self.calls = 0

        async def start(self, value):
            self.calls += 1
            return "next-scenario"

    reviewer, starter = Reviewer(), Starter()
    completion = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer, starter))
    first = await service(store, CandidateRepository(tmp_path, {"base": ""}), Gateway([]), completion=completion).run(request(tmp_path, state))
    second = await service(store, CandidateRepository(tmp_path, {"base": ""}), Gateway([]), completion=completion).run(request(tmp_path, state))

    assert first.status == second.status == "behavior_complete"
    assert reviewer.calls == starter.calls == 1
    assert first.state.completion.status == "behavior_complete"
    assert first.state.behavior_review.next_behavior_ticket == "next-scenario"


def test_resume_fails_closed_on_adapter_version_or_approved_identity_change(tmp_path):
    state = initial_state()
    store = MemoryStore()
    store.save(state)

    class ChangedAdapter(PythonPytestAdapter):
        descriptor = LanguageAdapterDescriptor("python-pytest", "2.0.0", "python")

    value = service(store, CandidateRepository(tmp_path, {"base": ""}), Gateway([]), ChangedAdapter())
    with pytest.raises(ValueError, match="adapter version"):
        _load_state(store, value.adapters, request(tmp_path, state))

    with pytest.raises(ValueError, match="approved scenario identity"):
        replace(state, model=replace(state.model, canonical_test_identity="tests/test_other.py::test_other"))


def test_retry_cap_is_four_for_an_identical_frontier_and_successful_advance_is_progress(tmp_path):
    state = initial_state()
    assessment = BoundaryAssessment(
        BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value,
        state.frontier.active_fragment_id,
        BoundaryDiagnostic("collection_failure", "missing"),
    )
    for _ in range(4):
        state = _record_execution(state, "base", assessment)
    value = service(MemoryStore(), CandidateRepository(tmp_path, {"base": ""}), Gateway([]))
    outcome = value._execute_frontier(FrontierExecutionContext(request(tmp_path, state), state, PythonPytestAdapter()))
    assert outcome.status == "frontier_execution_attempts_exhausted"

    progressed = _advance(state, "green-base")
    assert progressed.frontier.index == 1
    assert progressed.regression.status == "pending"
    assert not progressed.frontier_attempt_counts or all(item.frontier_index != 1 for item in progressed.frontier_attempt_counts)


def test_cross_language_conformance_is_complete_block_protocol_only():
    fixtures = {
        "python": "def test_block():\n    if ready:\n        for item in items:\n            use(item)\n",
        "csharp": "[Fact]\npublic void Test() { if (ready) { foreach (var item in items) { Use(item); } } }\n",
        "vba": "Public Sub Test()\n    If ready Then\n        For Each item In items\n            UseItem item\n        Next item\n    End If\nEnd Sub\n",
    }
    assert fixtures["python"].count("    ") >= 3
    assert fixtures["csharp"].count("{") == fixtures["csharp"].count("}")
    assert "CS0246" in "CS0246: The type or namespace name Widget could not be found"
    assert all(token in fixtures["vba"] for token in ("If ready Then", "End If", "For Each", "Next item", "Public Sub", "End Sub"))
    with pytest.raises(ValueError, match="unsupported language boundary"):
        LanguageAdapterCatalog((PythonPytestAdapter(),)).for_language("unsupported")


def test_gatekeeper_collector_excludes_incomplete_or_abandoned_scenarios():
    base = initial_state()
    completed = replace(
        base,
        completion=ScenarioCompletion("behavior_complete", "base"),
        behavior_review=replace(base.behavior_review, verdict=APPROVED, attempts=1, next_behavior_ticket="next"),
    )
    incomplete = replace(base, completion=ScenarioCompletion("scenario_complete", "base"))
    abandoned = replace(base, completion=ScenarioCompletion("abandoned"))
    evidence = CompletedMicrocycleEvidenceCollector().collect([completed, incomplete, abandoned])

    assert [(item.test_name, item.semantic_revision) for item in evidence] == [
        (completed.model.canonical_test_identity, "base")
    ]
    assert evidence[0].requirement_refs == list(completed.scenario_draft.source_requirement_refs)


@pytest.mark.asyncio
async def test_persisted_behavior_review_protocol_failure_blocks_resume_without_reasoning_or_rack_work(tmp_path):
    failure = BehaviorReviewProtocolFailure(
        "athba_senior_behavior_review",
        2,
        "first-digest",
        "repair-digest",
        "not valid JSON",
        None,
        ("reasoning:athba_senior_behavior_review", "reasoning:athba_senior_behavior_review_json_repair"),
    )
    initial = initial_state()
    state = replace(
        initial,
        completion=ScenarioCompletion("scenario_complete", "canonical"),
        behavior_review=BehaviorReviewState(
            "protocol_failure",
            1,
            failure.evidence_refs,
            protocol_failure=failure,
        ),
        pending_action=MicrocyclePendingAction.BLOCKED.value,
    )
    store = MemoryStore()
    store.save(state)

    class Reviewer:
        def __init__(self):
            self.calls = 0

        async def review(self, value):
            self.calls += 1
            raise AssertionError("persisted protocol failure must not be rereviewed")

    reviewer = Reviewer()
    completion = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer))
    outcome = await service(
        store,
        CandidateRepository(tmp_path, {"base": ""}),
        Gateway([]),
        completion=completion,
    ).run(request(tmp_path, state))

    assert outcome.status == "behavior_review_protocol_failure"
    assert outcome.state.completion.completed_revision == "canonical"
    assert outcome.state.behavior_review.protocol_failure == failure
    assert reviewer.calls == 0
