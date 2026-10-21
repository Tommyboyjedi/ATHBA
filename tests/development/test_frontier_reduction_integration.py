"""The reducer participates only in ordinary, fully verified promotion."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from core.development.deterministic_regression import REGRESSION_CLEAR
from core.development.frontier_reduction_integration import (
    FrontierReductionContext, reduce_frontier_candidate,
)
from core.development.microcycle_domain import (
    DeveloperAttempt, LanguageAdapterDescriptor, MicrocyclePendingAction,
    MicrocycleState, RegressionState, RetryCounts, ScenarioCompletion,
    ScenarioFragment, ScenarioFrontier, ScenarioIntentResult, ScenarioModel,
    TestScenarioDraft,
)
from core.development.production_reduction import ProductionReductionResult
from core.development.strict_microcycle import (
    StrictMicrocycleDependencies, StrictMicrocycleRequest, StrictMicrocycleService,
)
from core.development.strict_tdd_transitions import MicrocycleTransitionKind
from core.execution.rack_ai_contract import RepositoryBinding


class RecordingReducer:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def reduce(self, request):
        self.requests.append(request)
        return self.result


class MemoryStore:
    def __init__(self, state):
        self.state = state
        self.saved = []

    def load(self, scenario_id):
        return self.state

    def save(self, state):
        self.state = state
        self.saved.append(state)


def promotion_state():
    draft = TestScenarioDraft("scenario", "behavior", "opaque", "selected test",
                              "tests/frontier::current", "tests/frontier")
    fragments = (ScenarioFragment("one", "scenario", "opaque", "selected test", "current"),)
    return MicrocycleState(
        draft, ScenarioIntentResult("scenario", "approved", "selected", ("SRC-1",)),
        ScenarioModel("scenario", "opaque", "1", draft.canonical_test_identity,
                      draft.source, draft.test_path),
        fragments, ScenarioFrontier("scenario", 0, "one", ("one",)), "B", None,
        RetryCounts(), (),
        (DeveloperAttempt(1, 0, "R", "earlier"),
         DeveloperAttempt(1, 0, "I", "C", ("original-rack-evidence",))),
        RegressionState(REGRESSION_CLEAR, ("runtime", "test"), ("initial-green",)),
        ScenarioCompletion("pending"), candidate_chain_revision="C",
        pending_action=MicrocyclePendingAction.PROMOTE_CANONICAL_BASE.value,
    )


def context(tmp_path, state):
    request = StrictMicrocycleRequest(
        "project", "source.unit", tmp_path,
        RepositoryBinding("project", "main", "B"), state,
        ("tests/prior::accepted",), True,
    )
    return FrontierReductionContext(request, state, "opaque-adapter")


def result(state, revision="V"):
    return ProductionReductionResult(revision, state.regression, "reduction-evidence")


def test_exact_baseline_red_input_candidate_and_acceptance_are_forwarded(tmp_path):
    state = promotion_state()
    reducer = RecordingReducer(result(state))
    reduced = reduce_frontier_candidate(reducer, context(tmp_path, state))

    request = reducer.requests[0]
    assert (request.baseline_revision, request.accepted_red_revision,
            request.developer_input_revision, request.candidate_revision) == ("B", "R", "I", "C")
    assert request.production_paths == ("source.unit",)
    assert request.required_artifacts == ("source.unit",)
    assert request.current_frontier_test == "tests/frontier::current"
    assert request.regression_command == state.regression.command
    assert request.prior_completed_test_nodes == ("tests/prior::accepted",)
    assert request.include_accepted_suite is True
    assert request.adapter_id == "opaque-adapter"
    assert request.initial_regression == state.regression
    assert reduced.state.candidate_chain_revision == "V"
    assert reduced.state.development_base_revision == "B"
    assert reduced.state.developer_attempts == state.developer_attempts
    assert reduced.state.retry_counts == state.retry_counts
    assert state.developer_attempts[-1].candidate_revision == "C"


@pytest.mark.parametrize("change", [
    {"developer_attempts": ()},
    {"candidate_chain_revision": "already-green"},
    {"candidate_chain_revision": "regression-repair"},
    {"developer_attempts": (DeveloperAttempt(1, 1, "R", "C"),)},
])
def test_no_matching_ordinary_candidate_means_no_reduction(tmp_path, change):
    state = replace(promotion_state(), **change)
    reducer = RecordingReducer(result(state))
    reduced = reduce_frontier_candidate(reducer, context(tmp_path, state))
    assert reduced.state is state
    assert reducer.requests == []


def test_non_clear_regression_cannot_admit_reduction(tmp_path):
    state = replace(promotion_state(), regression=RegressionState("accumulated_regression", ("runtime", "test")))
    reducer = RecordingReducer(result(state))
    with pytest.raises(ValueError, match="requires a regression-clear"):
        reduce_frontier_candidate(reducer, context(tmp_path, state))
    assert reducer.requests == []


def test_unverified_reducer_output_cannot_be_promoted(tmp_path):
    state = promotion_state()
    reducer = RecordingReducer(ProductionReductionResult(
        "uncertain-trial", RegressionState("pending", ("runtime", "test")), "partial-evidence"))
    with pytest.raises(ValueError, match="no verified GREEN"):
        reduce_frontier_candidate(reducer, context(tmp_path, state))


def test_optional_seam_preserves_existing_fake_composition(tmp_path):
    state = promotion_state()
    assert reduce_frontier_candidate(None, context(tmp_path, state)).state is state


def service_for(state, reducer):
    store = MemoryStore(state)
    adapter = SimpleNamespace(descriptor=LanguageAdapterDescriptor("opaque-adapter", "1", "opaque"))
    catalog = SimpleNamespace(for_language=lambda language: adapter)
    forbidden = SimpleNamespace(execute=lambda *args: pytest.fail("model/runtime not required here"))
    service = StrictMicrocycleService(StrictMicrocycleDependencies(
        store, forbidden, forbidden, catalog, forbidden, production_reducer=reducer))
    return service, store


@pytest.mark.asyncio
async def test_public_advance_reduces_before_working_and_canonical_promotion(tmp_path, monkeypatch):
    from core.development import strict_microcycle_advance as transitions
    state = promotion_state()
    reducer = RecordingReducer(result(state))
    service, store = service_for(state, reducer)
    events = []
    monkeypatch.setattr(transitions, "_advance_working_revision",
                        lambda request, revision, kind, evidence: events.append(("working", revision, evidence)))
    monkeypatch.setattr(transitions, "_promote_canonical_revision",
                        lambda request, revision, evidence: events.append(("canonical", revision, evidence)))
    outcome = await service.advance(context(tmp_path, state).request)

    assert outcome.kind == MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED
    assert events == [("working", "V", "reduction-evidence"),
                      ("canonical", "V", "reduction-evidence")]
    assert store.saved[0].candidate_chain_revision == "V"
    assert store.saved[0].development_base_revision == "B"
    assert outcome.state.development_base_revision == "V"
    assert outcome.state.pending_action == MicrocyclePendingAction.ADVANCE_FRONTIER.value
    assert outcome.state.developer_attempts == state.developer_attempts


@pytest.mark.asyncio
async def test_resume_after_reduced_state_save_does_not_replay_model_or_reducer(tmp_path, monkeypatch):
    from core.development import strict_microcycle_advance as transitions
    state = promotion_state()
    reducer = RecordingReducer(result(state))
    service, store = service_for(state, reducer)
    monkeypatch.setattr(transitions, "_advance_working_revision", lambda *args: None)
    def interrupted(*args):
        raise RuntimeError("promotion interrupted")
    monkeypatch.setattr(transitions, "_promote_canonical_revision", interrupted)
    with pytest.raises(RuntimeError, match="promotion interrupted"):
        await service.advance(context(tmp_path, state).request)
    assert store.state.candidate_chain_revision == "V"
    assert store.state.development_base_revision == "B"
    promoted = []
    monkeypatch.setattr(transitions, "_promote_canonical_revision",
                        lambda request, revision, evidence: promoted.append(revision))
    outcome = await service.advance(context(tmp_path, state).request)
    assert promoted == ["V"]
    assert len(reducer.requests) == 1
    assert outcome.state.developer_attempts == state.developer_attempts
    assert outcome.state.retry_counts == state.retry_counts
