"""One persisted transition implementation for the strict microcycle."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from core.development.behavior_completion import APPROVED, REPAIR_REQUIRED, REPLAN_REQUIRED, BehaviorCompletionCommand
from core.development.behavior_repair import BehaviorRepairRequest
from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION,
    REGRESSION_CLEAR,
    REGRESSION_INFRASTRUCTURE_FAILURE,
    DeterministicRegressionRequest,
)
from core.development.microcycle_domain import (
    BoundaryClassificationRequest,
    BoundaryOutcome,
    FrontierExecutionRequest,
    FrontierMaterialisationRequest,
    LanguageTestAdapter,
    MicrocyclePendingAction,
    MicrocycleState,
    RegressionState,
    ScenarioCompletion,
)
from core.development.microcycle_revision_state import RevisionRecoveryRequest, RevisionTransitionKind
from core.development.strict_microcycle import (
    DeveloperExecutionContext,
    FrontierCandidateRequest,
    RegressionRepairContext,
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

if TYPE_CHECKING:
    from core.development.strict_microcycle import StrictMicrocycleService


async def advance(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
) -> MicrocycleAdvanceResult:
    """Perform exactly one persisted strict-TDD action."""
    stored = service.state_store.load(request.initial_state.scenario_draft.scenario_id)
    state = _normalise_pending_action(_load_state(service.state_store, service.adapters, request))
    prior_status = _status(state)
    if stored is None:
        return _result(MicrocycleTransitionKind.STATE_INITIALISED, prior_status, state, request)
    adapter = service.adapters.for_language(state.model.language_id)
    if state.completion.status == "behavior_complete":
        return _result(MicrocycleTransitionKind.BEHAVIOR_COMPLETED, prior_status, state, request, more=False)
    action = MicrocyclePendingAction(state.pending_action)
    if action == MicrocyclePendingAction.BLOCKED and state.behavior_review.verdict == "protocol_failure":
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker="behavior_review_protocol_failure", more=False)
    if action == MicrocyclePendingAction.BLOCKED and state.behavior_review.verdict == REPLAN_REQUIRED:
        return _result(
            MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED,
            prior_status,
            state,
            request,
            blocker=state.behavior_review.rationale,
        )
    if action == MicrocyclePendingAction.OBSERVE_FRONTIER:
        return _observe_frontier(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.SUBMIT_DEVELOPER:
        return await _submit_developer(service, request, state, prior_status)
    if action == MicrocyclePendingAction.VERIFY_DEVELOPER_GREEN:
        return _verify_developer_green(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.RUN_REGRESSION:
        return _run_regression(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.PROMOTE_CANONICAL_BASE:
        return _promote_canonical_base(service, request, state, prior_status)
    if action == MicrocyclePendingAction.SUBMIT_REGRESSION_REPAIR:
        return await _submit_regression_repair(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.VERIFY_REGRESSION_REPAIR:
        return _verify_regression_repair(service, request, state, prior_status)
    if action == MicrocyclePendingAction.RUN_REPAIR_REGRESSION:
        return _run_repair_regression(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.PROMOTE_REGRESSION_REPAIR:
        return _promote_regression_repair(service, request, state, prior_status)
    if action == MicrocyclePendingAction.ADVANCE_FRONTIER:
        return _advance_frontier(service, request, state, prior_status)
    if action == MicrocyclePendingAction.REVIEW_BEHAVIOR:
        return await _review_behavior(service, request, state, prior_status)
    if action == MicrocyclePendingAction.SUBMIT_BEHAVIOR_REPAIR:
        return await _submit_behavior_repair(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.VERIFY_BEHAVIOR_REPAIR:
        return _verify_behavior_repair(service, request, state, prior_status)
    if action == MicrocyclePendingAction.RUN_BEHAVIOR_REPAIR_REGRESSION:
        return _run_behavior_repair_regression(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.PROMOTE_BEHAVIOR_REPAIR:
        return _promote_behavior_repair(service, request, state, adapter, prior_status)
    if action == MicrocyclePendingAction.COMPLETE_BEHAVIOR:
        return await _complete_behavior(service, request, state, prior_status)
    return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker=state.pending_action)


def _observe_frontier(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    base = state.candidate_chain_revision or state.development_base_revision
    artifact = adapter.materialise_frontier(
        FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, base)
    )
    candidate = service.candidates.materialise(
        FrontierCandidateRequest(artifact, request.repository_root, state.model.test_path)
    )
    try:
        diagnostic = adapter.execute_frontier(
            FrontierExecutionRequest(candidate.artifact, str(candidate.project_root), state.model.test_path, request.production_path)
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
            updated = replace(
                updated,
                current_accepted_red_revision=candidate.candidate_revision,
                pending_action=MicrocyclePendingAction.SUBMIT_DEVELOPER.value,
            )
            service.state_store.save(updated)
            return _result(MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED, prior_status, updated, request)
        if assessment.outcome == BoundaryOutcome.GREEN.value:
            _advance_working_revision(
                request,
                candidate.candidate_revision,
                RevisionTransitionKind.FRONTIER_ACCEPTED.value,
                None,
            )
            updated = replace(
                updated,
                candidate_chain_revision=candidate.candidate_revision,
                pending_action=MicrocyclePendingAction.RUN_REGRESSION.value,
            )
            service.state_store.save(updated)
            return _result(MicrocycleTransitionKind.PASSING_FRONTIER_OBSERVED, prior_status, updated, request)
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        service.state_store.save(updated)
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, updated, request, blocker=assessment.outcome)
    finally:
        service.candidates.cleanup(candidate)


async def _submit_developer(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    updated, outcome = await service._developer(DeveloperExecutionContext(request, state))
    if outcome.status == "advanced":
        updated = replace(updated, pending_action=MicrocyclePendingAction.VERIFY_DEVELOPER_GREEN.value)
        kind = MicrocycleTransitionKind.DEVELOPER_CANDIDATE_ACCEPTED
        blocker = None
    elif outcome.status == "developer_candidate_rejected":
        updated = replace(updated, pending_action=MicrocyclePendingAction.SUBMIT_DEVELOPER.value)
        kind = MicrocycleTransitionKind.DEVELOPER_CANDIDATE_REJECTED
        blocker = None
    elif outcome.status.endswith("exhausted"):
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED
        blocker = outcome.status
    else:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = outcome.status
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, rack_ai=outcome.developer_submissions == 1, blocker=blocker)


def _verify_developer_green(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    base = state.candidate_chain_revision or state.development_base_revision
    artifact = adapter.materialise_frontier(
        FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, base)
    )
    candidate = service.candidates.materialise(
        FrontierCandidateRequest(artifact, request.repository_root, state.model.test_path)
    )
    try:
        diagnostic = adapter.execute_frontier(
            FrontierExecutionRequest(candidate.artifact, str(candidate.project_root), state.model.test_path, request.production_path)
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
        if assessment.outcome == BoundaryOutcome.GREEN.value:
            updated = replace(updated, pending_action=MicrocyclePendingAction.RUN_REGRESSION.value)
            kind = MicrocycleTransitionKind.GREEN_VERIFIED
            blocker = None
        elif assessment.outcome in _VALID_RED_OUTCOMES:
            updated = replace(
                updated,
                current_accepted_red_revision=base,
                pending_action=MicrocyclePendingAction.SUBMIT_DEVELOPER.value,
            )
            kind = MicrocycleTransitionKind.GREEN_VERIFIED
            blocker = None
        else:
            updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
            kind = MicrocycleTransitionKind.BLOCKED
            blocker = assessment.outcome
        service.state_store.save(updated)
        return _result(kind, prior_status, updated, request, blocker=blocker)
    finally:
        service.candidates.cleanup(candidate)


def _run_regression(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    revision = state.candidate_chain_revision or state.development_base_revision
    artifact = adapter.materialise_frontier(
        FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, revision)
    )
    candidate = service.candidates.materialise(
        FrontierCandidateRequest(artifact, request.repository_root, state.model.test_path)
    )
    try:
        regression = service.regression.run(
            DeterministicRegressionRequest(
                candidate.project_root,
                state.regression.command,
                artifact.canonical_test_identity,
                request.prior_completed_test_nodes,
                request.include_accepted_regression_suite,
            )
        )
    finally:
        service.candidates.cleanup(candidate)
    updated = replace(state, regression=regression.state(state.regression.command))
    if regression.status == REGRESSION_CLEAR:
        updated = replace(updated, pending_action=MicrocyclePendingAction.PROMOTE_CANONICAL_BASE.value)
        kind = MicrocycleTransitionKind.REGRESSION_CLEAR
        blocker = None
    elif regression.status == ACCUMULATED_REGRESSION:
        updated = replace(updated, pending_action=MicrocyclePendingAction.SUBMIT_REGRESSION_REPAIR.value)
        kind = MicrocycleTransitionKind.ACCUMULATED_REGRESSION
        blocker = None
    elif regression.status == REGRESSION_INFRASTRUCTURE_FAILURE:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.REGRESSION_INFRASTRUCTURE_FAILURE
        blocker = regression.status
    else:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = regression.status
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, regression=True, blocker=blocker)


async def _submit_regression_repair(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    updated, outcome = await service.repair_service.submit(
        RegressionRepairContext(request, state, adapter)
    )
    if outcome.status == "regression_repair_submitted":
        updated = replace(updated, pending_action=MicrocyclePendingAction.VERIFY_REGRESSION_REPAIR.value)
        kind = MicrocycleTransitionKind.REGRESSION_REPAIR_SUBMITTED
        blocker = None
    elif outcome.status.endswith("exhausted"):
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED
        blocker = outcome.status
    else:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = outcome.status
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, rack_ai=outcome.developer_submissions == 1, blocker=blocker)


def _verify_regression_repair(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if state.candidate_chain_revision is None:
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker="missing_regression_repair_candidate")
    updated = replace(state, pending_action=MicrocyclePendingAction.RUN_REPAIR_REGRESSION.value)
    service.state_store.save(updated)
    return _result(MicrocycleTransitionKind.REGRESSION_REPAIR_VERIFIED, prior_status, updated, request)


def _run_repair_regression(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    updated, outcome = service.repair_service.run_regression(
        RegressionRepairContext(request, state, adapter)
    )
    if outcome.status == "green":
        updated = replace(updated, pending_action=MicrocyclePendingAction.PROMOTE_REGRESSION_REPAIR.value)
        kind = MicrocycleTransitionKind.REGRESSION_REPAIR_CLEARED
        blocker = None
    else:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = outcome.status
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, regression=True, blocker=blocker)


def _promote_regression_repair(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    updated = service.repair_service.promote(request, state)
    updated = replace(updated, pending_action=MicrocyclePendingAction.ADVANCE_FRONTIER.value)
    service.state_store.save(updated)
    return _result(MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED, prior_status, updated, request)


def _promote_canonical_base(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    revision = state.candidate_chain_revision or state.development_base_revision
    _promote_canonical_revision(request, revision, None)
    updated = replace(
        state,
        development_base_revision=revision,
        candidate_chain_revision=revision,
        pending_action=MicrocyclePendingAction.ADVANCE_FRONTIER.value,
    )
    service.state_store.save(updated)
    return _result(MicrocycleTransitionKind.CANONICAL_BASE_PROMOTED, prior_status, updated, request)


def _advance_frontier(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if state.frontier.index == len(state.fragments) - 1:
        updated = replace(
            state,
            completion=ScenarioCompletion("scenario_complete", state.development_base_revision),
            pending_action=MicrocyclePendingAction.REVIEW_BEHAVIOR.value,
        )
        kind = MicrocycleTransitionKind.SCENARIO_COMPLETED
    else:
        updated = replace(
            _advance(state, state.development_base_revision),
            pending_action=MicrocyclePendingAction.OBSERVE_FRONTIER.value,
        )
        kind = MicrocycleTransitionKind.FRONTIER_ADVANCED
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request)


async def _review_behavior(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if service.behavior_completion is None:
        return _result(MicrocycleTransitionKind.SCENARIO_COMPLETED, prior_status, state, request, more=False)
    command = BehaviorCompletionCommand(state, persist=service.state_store.save)
    updated = await service.behavior_completion.review(command)
    if updated.behavior_review.verdict == APPROVED:
        updated = replace(updated, pending_action=MicrocyclePendingAction.COMPLETE_BEHAVIOR.value)
        kind = MicrocycleTransitionKind.BEHAVIOR_REVIEW_APPROVED
        blocker = None
    elif updated.behavior_review.verdict == REPAIR_REQUIRED:
        updated = replace(updated, pending_action=MicrocyclePendingAction.SUBMIT_BEHAVIOR_REPAIR.value)
        kind = MicrocycleTransitionKind.BEHAVIOR_REVIEW_REPAIR_REQUIRED
        blocker = None
    elif updated.behavior_review.verdict == REPLAN_REQUIRED:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED
        blocker = updated.behavior_review.rationale
    else:
        updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = "behavior_review_protocol_failure" if updated.behavior_review.verdict == "protocol_failure" else updated.behavior_review.verdict
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, reasoning=True, blocker=blocker)



def _behavior_repair_request(
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
) -> BehaviorRepairRequest:
    return BehaviorRepairRequest(
        request.project_id,
        request.production_path,
        request.repository_root,
        request.repository_binding,
        state,
        adapter,
        request.prior_completed_test_nodes,
        request.include_accepted_regression_suite,
        request.revision_lifecycle,
        request.revision_binding_request,
    )


async def _submit_behavior_repair(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if service.behavior_repair is None:
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker="behavior_repair_unavailable")
    outcome = await service.behavior_repair.submit(_behavior_repair_request(request, state, adapter))
    if outcome.status == "behavior_repair_submitted":
        updated = replace(
            outcome.state,
            pending_action=MicrocyclePendingAction.VERIFY_BEHAVIOR_REPAIR.value,
        )
        kind = MicrocycleTransitionKind.BEHAVIOR_REPAIR_SUBMITTED
        blocker = None
    elif outcome.status.endswith("exhausted"):
        updated = replace(outcome.state, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED
        blocker = outcome.status
    else:
        updated = replace(outcome.state, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = outcome.status
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, rack_ai=outcome.developer_submissions == 1, blocker=blocker)


def _verify_behavior_repair(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    repair = state.behavior_review.repair
    if repair.execution is None or repair.current_candidate_revision is None:
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker="missing_behavior_repair_candidate")
    updated = replace(state, pending_action=MicrocyclePendingAction.RUN_BEHAVIOR_REPAIR_REGRESSION.value)
    service.state_store.save(updated)
    return _result(MicrocycleTransitionKind.BEHAVIOR_REPAIR_VERIFIED, prior_status, updated, request)


def _run_behavior_repair_regression(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if service.behavior_repair is None:
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker="behavior_repair_unavailable")
    outcome = service.behavior_repair.run_regression(_behavior_repair_request(request, state, adapter))
    if outcome.status == "behavior_repair_regression_clear":
        updated = replace(
            outcome.state,
            pending_action=MicrocyclePendingAction.PROMOTE_BEHAVIOR_REPAIR.value,
        )
        kind = MicrocycleTransitionKind.BEHAVIOR_REPAIR_REGRESSION_CLEAR
        blocker = None
    else:
        updated = replace(outcome.state, pending_action=MicrocyclePendingAction.BLOCKED.value)
        kind = MicrocycleTransitionKind.BLOCKED
        blocker = outcome.status
    service.state_store.save(updated)
    return _result(kind, prior_status, updated, request, regression=True, blocker=blocker)


def _promote_behavior_repair(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if service.behavior_repair is None:
        return _result(MicrocycleTransitionKind.BLOCKED, prior_status, state, request, blocker="behavior_repair_unavailable")
    outcome = service.behavior_repair.promote(_behavior_repair_request(request, state, adapter))
    updated = replace(outcome.state, pending_action=MicrocyclePendingAction.REVIEW_BEHAVIOR.value)
    service.state_store.save(updated)
    return _result(MicrocycleTransitionKind.BEHAVIOR_REPAIR_REGRESSION_CLEAR, prior_status, updated, request)


async def _complete_behavior(
    service: StrictMicrocycleService,
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    prior_status: str,
) -> MicrocycleAdvanceResult:
    if service.behavior_completion is None:
        return _result(MicrocycleTransitionKind.SCENARIO_COMPLETED, prior_status, state, request, more=False)
    updated = await service.behavior_completion.complete_approved(
        BehaviorCompletionCommand(state, persist=service.state_store.save)
    )
    updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
    _complete_revision_lifecycle(request, updated)
    service.state_store.save(updated)
    return _result(MicrocycleTransitionKind.BEHAVIOR_COMPLETED, prior_status, updated, request, more=False)


def _normalise_pending_action(state: MicrocycleState) -> MicrocycleState:
    if state.pending_action != MicrocyclePendingAction.OBSERVE_FRONTIER.value:
        return state
    if state.completion.status == "scenario_complete":
        return replace(state, pending_action=MicrocyclePendingAction.REVIEW_BEHAVIOR.value)
    if state.regression.status == REGRESSION_CLEAR:
        return replace(state, pending_action=MicrocyclePendingAction.PROMOTE_CANONICAL_BASE.value)
    if state.current_accepted_red_revision is not None:
        return replace(state, pending_action=MicrocyclePendingAction.SUBMIT_DEVELOPER.value)
    return state


def _status(state: MicrocycleState) -> str:
    if state.completion.status != "pending":
        return state.completion.status
    return state.pending_action


def _result(
    kind: MicrocycleTransitionKind,
    prior_status: str,
    state: MicrocycleState,
    request: StrictMicrocycleRequest,
    reasoning: bool = False,
    rack_ai: bool = False,
    regression: bool = False,
    blocker: str | None = None,
    more: bool | None = None,
) -> MicrocycleAdvanceResult:
    lifecycle = None
    if request.revision_lifecycle is not None and request.revision_binding_request is not None:
        lifecycle = request.revision_lifecycle.recover(
            RevisionRecoveryRequest(request.revision_binding_request.scenario_id)
        )
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
        (
            state.retry_counts.developer,
            state.retry_counts.regression,
            state.retry_counts.frontier_execution,
            len(state.developer_attempts),
        ),
        state.pending_action,
    )
    evidence = tuple(state.regression.evidence_refs) + tuple(state.behavior_review.evidence_refs)
    terminal = {
        MicrocycleTransitionKind.BLOCKED,
        MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED,
        MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED,
        MicrocycleTransitionKind.BEHAVIOR_COMPLETED,
    }
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
        kind not in terminal if more is None else more,
        blocker,
        fingerprint,
        state,
    )
