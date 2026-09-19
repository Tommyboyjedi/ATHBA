from types import SimpleNamespace
from typing import cast

from core.development.scenario_drafting_domain import MicrocycleState, ScenarioDraftAttempt, ScenarioDraftRunState
from core.development.strict_tdd_feature_application import FeatureScenarioResult
from core.development.project_environment import DevelopmentProject
from core.development.strict_tdd_feature_application_advance import _result_for
from core.development.strict_tdd_feature_domain import StrictTddFeatureState, StrictTddFeatureStatus
from core.development.strict_tdd_feature_execution_advance import _fingerprint
from core.development.strict_tdd_transitions import (
    FeatureTransitionKind,
    ScenarioAdvanceResult,
    ScenarioTransitionKind,
    TransitionFingerprint,
)


def _attempt(number: int, revision: str | None = None) -> ScenarioDraftAttempt:
    return ScenarioDraftAttempt(number, f"attempt-{number}", None, revision, None, "candidate_submitted" if revision else "worker_model_timeout")


def _draft_state(*attempts: ScenarioDraftAttempt, status: str = "drafting", approved: bool = False) -> ScenarioDraftRunState:
    return ScenarioDraftRunState(
        "example-widget--B-1", "B-1", ("SRC-1",), "python", "pytest", "tests/test_example_widget.py", "a" * 40,
        attempts, cast(MicrocycleState, object()) if approved else None, "approved" if approved else status,
    )


def _outcome() -> FeatureScenarioResult:
    return FeatureScenarioResult("B-1", "example-widget--B-1", "drafting", "refs/heads/main", "a" * 40, None, None)


def _request():
    return SimpleNamespace(behavior=SimpleNamespace(ref="B-1"))


def test_scenario_fingerprint_tracks_timeout_attempt_progress_and_candidate_action():
    first = _fingerprint(_outcome(), _request(), _draft_state(_attempt(1)), None)
    second = _fingerprint(_outcome(), _request(), _draft_state(_attempt(1), _attempt(2)), None)
    candidate = _fingerprint(_outcome(), _request(), _draft_state(_attempt(1), _attempt(2, "b" * 40)), None)

    assert first != second
    assert first.pending_action == second.pending_action == "scenario_draft_submission"
    assert candidate.pending_action == "scenario_intent_review"
    assert candidate.working_sha == "b" * 40


def test_scenario_lifts_nested_microcycle_stable_identity():
    first_child = TransitionFingerprint("running", "B-1", "example-widget--B-1", 0, "a" * 40, "b" * 40, (0,), "green")
    second_child = TransitionFingerprint("running", "B-1", "example-widget--B-1", 1, "a" * 40, "c" * 40, (1,), "regression")
    same_child = TransitionFingerprint("running", "B-1", "example-widget--B-1", 0, "a" * 40, "b" * 40, (0,), "green")

    first = _fingerprint(_outcome(), _request(), _draft_state(_attempt(1, "b" * 40), approved=True), first_child)
    second = _fingerprint(_outcome(), _request(), _draft_state(_attempt(1, "b" * 40), approved=True), second_child)
    same = _fingerprint(_outcome(), _request(), _draft_state(_attempt(1, "b" * 40), approved=True), same_child)

    assert first != second
    assert first == same
    assert second.frontier_index == 1
    assert second.pending_action == "regression"


def _scenario(fingerprint: TransitionFingerprint) -> ScenarioAdvanceResult:
    outcome = _outcome()
    return ScenarioAdvanceResult(
        ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED, "drafting", "drafting", "B-1", "example-widget--B-1",
        "refs/heads/main", "a" * 40, None, None, (), False, False, True, None, fingerprint, outcome,
    )


def test_feature_wrapper_preserves_nested_scenario_identity():
    state = StrictTddFeatureState("example-widget", "source-hash", StrictTddFeatureStatus.RUNNING.value, current_scenario_id="example-widget--B-1", canonical_ref="refs/heads/main", canonical_development_base="a" * 40)
    project = cast(DevelopmentProject, SimpleNamespace(repository_root="/tmp/example-widget"))
    first_nested = TransitionFingerprint("drafting", "B-1", "example-widget--B-1", None, "a" * 40, None, (1,), "scenario_draft_submission")
    second_nested = TransitionFingerprint("drafting", "B-1", "example-widget--B-1", None, "a" * 40, "b" * 40, (2,), "scenario_intent_review")

    first = _result_for(FeatureTransitionKind.SCENARIO_ADVANCED, state, project, behavior_ref="B-1", scenario_transition=_scenario(first_nested))
    second = _result_for(FeatureTransitionKind.SCENARIO_ADVANCED, state, project, behavior_ref="B-1", scenario_transition=_scenario(second_nested))

    assert first.fingerprint != second.fingerprint
    assert second.fingerprint.retry_counts == (0, 2)
    assert second.fingerprint.pending_action == "scenario_intent_review"
