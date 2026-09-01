"""One-persisted-transition implementation for the strict microcycle."""
from __future__ import annotations

from dataclasses import replace

from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION,
    REGRESSION_CLEAR,
    REGRESSION_INFRASTRUCTURE_FAILURE,
    DeterministicRegressionRequest,
)
from core.development.microcycle_domain import (
    BoundaryOutcome,
    BoundaryClassificationRequest,
    FrontierExecutionRequest,
    FrontierMaterialisationRequest,
    RegressionState,
    ScenarioCompletion,
)
from core.development.microcycle_revision_state import RevisionRecoveryRequest, RevisionTransitionKind
from core.development.strict_microcycle import (
    FrontierCandidateRequest,
    FrontierExecutionContext,
    StrictMicrocycleRequest,
    _VALID_RED_OUTCOMES,
    _advance,
    _advance_working_revision,
    _complete_revision_lifecycle,
    _load_state,
    _promote_canonical_revision,
    _record_execution,
)
from core.development.strict_tdd_transitions import (
    MicrocycleAdvanceResult,
    MicrocycleTransitionKind,
    TransitionFingerprint,
)


async def advance(service: object, request: StrictMicrocycleRequest) -> MicrocycleAdvanceResult:
    """Perform and persist exactly one strict-microcycle workflow transition."""
    state_store = getattr(service, "state_store")
    stored = state_store.load(request.initial_state.scenario_draft.scenario_id)
    state = _load_state(state_store, getattr(service, "adapters"), request)
    prior_status = _status(state)
    if stored is None:
        return _result(MicrocycleTransitionKind.STATE_INITIALISED, prior_status, state, request)
    adapter = getattr(service, "adapters").for_language(state.model.language_id)
    if state.completion.status == "behavior_complete":
        _complete_revision_lifecycle(request, state)
        return _result(MicrocycleTransitionKind.BEHAVIOR_COMPLETED, prior_status, state, request)
    if state.completion.status == "scenario_complete":
        return await _advance_completed_behavior(service, request, state, adapter, prior_status)
    if state.regression.status == REGRESSION_CLEAR:
        return _advance_after_regression(service, request, state, prior_status)
    if state.regression.status == ACCUMULATED_REGRESSION:
        return await _advance_regression_repair(service, request, state, adapter, prior_status)
    if state.current_accepted_red_revision is not None:
        updated, outcome = await getattr(service, "_developer")(type("Context", (), {"request": request, "state": state})())
        kind = _developer_kind(outcome.status)
        blocker = outcome.status if kind == MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED else None
        return _result(kind, prior_status, updated, request, rack_ai=outcome.developer_submissions == 1, blocker=blocker)
    if _green_is_waiting_for_regression(state):
        return _run_regression(service, request, state, adapter, prior_status)
    return _observe_frontier(service, request, state, adapter, prior_status)


def _observe_frontier(
    service: object,
    request: StrictMicrocycleRequest,
    state: object,
    adapter: object,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    base = state.candidate_chain_revision or state.development_base_revision
    artifact = adapter.materialise_frontier(
        FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, base)
    )
    candidate = getattr(service, "candidates").materialise(
        FrontierCandidateRequest(artifact, request.repository_root, state.model.test_path)
    )
    try:
        diagnostic = adapter.execute_frontier(
            FrontierExecutionRequest(candidate.artifact, str(candidate.project_root), state.model.test_path)
        )
        previous = BoundaryOutcome.GREEN.value if state.frontier.index else None
        assessment = adapter.classify_boundary(
            BoundaryClassificationRequest(
                diagnostic,
                candidate.artifact,
                state.fragments[state.frontier.index],
                previous,
            )
        )
        updated = _record_execution(state, base, assessment)
        if assessment.outcome in _VALID_RED_OUTCOMES:
            _advance_working_revision(
                request,
                candidate.candidate_revision,
                RevisionTransitionKind.FRONTIER_ACCEPTED.value,
                None,
            )
            updated = replace(updated, current_accepted_red_revision=candidate.candidate_revision)
            getattr(service, "state_store").save(updated)
            return _result(MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED, prior_status, updated, request)
        if assessment.outcome == BoundaryOutcome.GREEN.value:
            _advance_working_revision(
                request,
                candidate.candidate_revision,
                RevisionTransitionKind.FRONTIER_ACCEPTED.value,
                None,
            )
            updated = replace(updated, candidate_chain_revision=candidate.candidate_revision)
            getattr(service, "state_store").save(updated)
            return _result(MicrocycleTransitionKind.PASSING_FRONTIER_OBSERVED, prior_status, updated, request)
        getattr(service, "state_store").save(updated)
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, updated, request, blocker=assessment.outcome)
    finally:
        getattr(service, "candidates").cleanup(candidate)


def _run_regression(
    service: object,
    request: StrictMicrocycleRequest,
    state: object,
    adapter: object,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    revision = state.candidate_chain_revision or state.development_base_revision
    artifact = adapter.materialise_frontier(
        FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, revision)
    )
    candidate = getattr(service, "candidates").materialise(
        FrontierCandidateRequest(artifact, request.repository_root, state.model.test_path)
    )
    try:
        regression = getattr(service, "regression").run(
            DeterministicRegressionRequest(
                candidate.project_root,
                state.regression.command,
                artifact.canonical_test_identity,
                request.prior_completed_test_nodes,
                request.include_accepted_regression_suite,
            )
        )
    finally:
        getattr(service, "candidates").cleanup(candidate)
    updated = replace(state, regression=regression.state(state.regression.command))
    if regression.status == REGRESSION_CLEAR:
        _promote_canonical_revision(request, revision, None)
        updated = replace(
            updated,
            candidate_chain_revision=revision,
            development_base_revision=revision,
        )
        kind = MicrocycleTransitionKind.REGRESSION_CLEAR
    elif regression.status == ACCUMULATED_REGRESSION:
        kind = MicrocycleTransitionKind.ACCUMULATED_REGRESSION
    elif regression.status == REGRESSION_INFRASTRUCTURE_FAILURE:
        kind = MicrocycleTransitionKind.REGRESSION_INFRASTRUCTURE_FAILURE
    else:
        kind = MicrocycleTransitionKind.BLOCKED
    getattr(service, "state_store").save(updated)
    return _result(kind, prior_status, updated, request, regression=True, blocker=None if kind != MicrocycleTransitionKind.BLOCKED else regression.status)


def _advance_after_regression(
    service: object,
    request: StrictMicrocycleRequest,
    state: object,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if state.frontier.index == len(state.fragments) - 1:
        updated = replace(state, completion=ScenarioCompletion("scenario_complete", state.development_base_revision))
        getattr(service, "state_store").save(updated)
        return _result(MicrocycleTransitionKind.SCENARIO_COMPLETED, prior_status, updated, request)
    updated = _advance(state, state.development_base_revision)
    getattr(service, "state_store").save(updated)
    return _result(MicrocycleTransitionKind.FRONTIER_ADVANCED, prior_status, updated, request)


async def _advance_regression_repair(
    service: object,
    request: StrictMicrocycleRequest,
    state: object,
    adapter: object,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    context = type("Context", (), {"request": request, "state": state, "adapter": adapter})()
    updated, outcome = await getattr(service, "repair_service").repair(context)
    if outcome.status == "green":
        kind = MicrocycleTransitionKind.REGRESSION_REPAIR_CLEARED
    elif outcome.status.endswith("exhausted"):
        kind = MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED
    else:
        kind = MicrocycleTransitionKind.REGRESSION_REPAIR_SUBMITTED
    return _result(kind, prior_status, updated, request, rack_ai=outcome.developer_submissions == 1, regression=True, blocker=None if kind != MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED else outcome.status)


async def _advance_completed_behavior(
    service: object,
    request: StrictMicrocycleRequest,
    state: object,
    adapter: object,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    completion = getattr(service, "behavior_completion")
    if completion is None:
        return _result(MicrocycleTransitionKind.SCENARIO_COMPLETED, prior_status, state, request, more=False)
    review = state.behavior_review
    if review.verdict == "pending":
        updated = await completion.review(type("Command", (), {"state": state, "production_diff": "", "persist": getattr(service, "state_store").save})())
        kind = _review_kind(updated.behavior_review.verdict)
        return _result(kind, prior_status, updated, request, reasoning=True)
    if review.verdict == "approved":
        updated = await completion.complete_approved(type("Command", (), {"state": state, "production_diff": "", "persist": getattr(service, "state_store").save})())
        _complete_revision_lifecycle(request, updated)
        return _result(MicrocycleTransitionKind.BEHAVIOR_COMPLETED, prior_status, updated, request)
    if review.verdict == "replan_required":
        return _result(MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED, prior_status, state, request, blocker=review.rationale)
    if review.verdict == "repair_required" and getattr(service, "behavior_repair") is not None:
        repair_request = getattr(service, "_behavior_repair_request", None)
        if repair_request is None:
            from core.development.strict_microcycle import _behavior_repair_request
            repair_request = _behavior_repair_request
        outcome = await getattr(service, "behavior_repair").repair(repair_request(request, state, adapter))
        kind = MicrocycleTransitionKind.BEHAVIOR_REPAIR_REGRESSION_CLEAR if outcome.status == "behavior_repair_regression_clear" else MicrocycleTransitionKind.BEHAVIOR_REPAIR_SUBMITTED
        return _result(kind, prior_status, outcome.state, request, rack_ai=outcome.developer_submissions == 1, regression=True)
    return _result(MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED, prior_status, state, request, blocker=review.verdict)


def _developer_kind(status: str) -> MicrocycleTransitionKind:
    if status == "advanced":
        return MicrocycleTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED
    if status == "developer_candidate_rejected":
        return MicrocycleTransitionKind.DEVELOPER_CANDIDATE_REJECTED
    if status.endswith("exhausted"):
        return MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED
    return MicrocycleTransitionKind.BLOCKED


def _review_kind(verdict: str) -> MicrocycleTransitionKind:
    if verdict == "approved":
        return MicrocycleTransitionKind.BEHAVIOR_REVIEW_APPROVED
    if verdict == "repair_required":
        return MicrocycleTransitionKind.BEHAVIOR_REVIEW_REPAIR_REQUIRED
    if verdict == "replan_required":
        return MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED
    return MicrocycleTransitionKind.BLOCKED


def _green_is_waiting_for_regression(state: object) -> bool:
    if not state.boundary_evidence:
        return False
    return (
        state.boundary_evidence[-1].outcome == BoundaryOutcome.GREEN.value
        and state.regression.status == "pending"
        and state.candidate_chain_revision != state.development_base_revision
    )


def _status(state: object) -> str:
    if state.completion.status != "pending":
        return state.completion.status
    if state.current_accepted_red_revision is not None:
        return "accepted_red"
    return state.regression.status


def _result(
    kind: MicrocycleTransitionKind,
    prior_status: str,
    state: object,
    request: StrictMicrocycleRequest,
    reasoning: bool = False,
    rack_ai: bool = False,
    regression: bool = False,
    blocker: str | None = None,
    more: bool | None = None,
) -> MicrocycleAdvanceResult:
    lifecycle = None
    if request.revision_lifecycle is not None and request.revision_binding_request is not None:
        lifecycle = request.revision_lifecycle.recover(RevisionRecoveryRequest(request.revision_binding_request.scenario_id))
    canonical_ref = lifecycle.canonical_ref if lifecycle is not None else request.repository_binding.base_ref
    canonical_sha = lifecycle.canonical_development_base if lifecycle is not None else state.development_base_revision
    working_ref = lifecycle.working_ref if lifecycle is not None and lifecycle.status != "behavior_complete" else None
    working_sha = lifecycle.working_revision if lifecycle is not None and lifecycle.status != "behavior_complete" else None
    fingerprint = TransitionFingerprint(
        _status(state),
        state.scenario_draft.behavior_ref,
        state.scenario_draft.scenario_id,
        state.frontier.index,
        canonical_sha,
        working_sha or state.candidate_chain_revision,
        (state.retry_counts.developer, state.retry_counts.regression, state.retry_counts.frontier_execution, len(state.developer_attempts)),
        _pending_action(state),
    )
    evidence = tuple(state.regression.evidence_refs) + tuple(state.behavior_review.evidence_refs)
    return MicrocycleAdvanceResult(
        kind,
        prior_status,
        _status(state),
        request.project_id,
        state.scenario_draft.behavior_ref,
        state.scenario_draft.scenario_id,
        state.frontier.index,
        canonical_ref,
        canonical_sha,
        working_ref,
        working_sha,
        state.candidate_chain_revision or state.current_accepted_red_revision,
        evidence,
        reasoning,
        rack_ai,
        regression,
        kind not in {MicrocycleTransitionKind.BLOCKED, MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED, MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED, MicrocycleTransitionKind.BEHAVIOR_COMPLETED} if more is None else more,
        blocker,
        fingerprint,
        state,
    )


def _pending_action(state: object) -> str:
    if state.completion.status == "scenario_complete":
        return "behavior_review"
    if state.current_accepted_red_revision is not None:
        return "developer"
    if state.regression.status == REGRESSION_CLEAR:
        return "frontier_advance"
    if state.regression.status == ACCUMULATED_REGRESSION:
        return "regression_repair"
    if _green_is_waiting_for_regression(state):
        return "deterministic_regression"
    return "frontier_execution"
