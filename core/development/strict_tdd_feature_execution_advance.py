"""One-transition scenario executor beneath the strict-TDD feature application."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from core.development.microcycle_revision_lifecycle import MicrocycleRevisionStateNotFound
from core.development.microcycle_revision_state import (
    MicrocycleRevisionState,
    RevisionBindingRequest,
    RevisionInitialisationRequest,
    RevisionRecoveryRequest,
)
from core.development.scenario_drafting_domain import ScenarioDraftRequest, ScenarioDraftRunState
from core.development.strict_microcycle import StrictMicrocycleRequest
from core.development.strict_tdd_feature_application import FeatureScenarioRequest, FeatureScenarioResult
from core.development.strict_tdd_feature_execution import _evidence, _facts, _ticket_for
from core.development.strict_tdd_transitions import (
    ScenarioAdvanceResult,
    ScenarioTransitionKind,
    TransitionFingerprint,
)

if TYPE_CHECKING:
    from core.development.strict_tdd_feature_execution import StrictFeatureScenarioExecutor

MAX_SCENARIO_COMPATIBILITY_TRANSITIONS = 100


async def advance(
    executor: StrictFeatureScenarioExecutor,
    request: FeatureScenarioRequest,
) -> ScenarioAdvanceResult:
    scenario_id = f"{request.project.project_id}--{request.behavior.ref}"
    draft_state = executor.drafting.state_store.load(scenario_id)
    if draft_state is None:
        return await _submit_draft(executor, request, scenario_id)
    if draft_state.approved_microcycle is None:
        if _intent_review_is_pending(draft_state):
            return await _review_intent(executor, request, scenario_id)
        return await _submit_draft(executor, request, scenario_id)
    binding_request = RevisionBindingRequest(
        scenario_id,
        request.project.project_id,
        request.project.repository_root,
        tuple(request.project.runtime.resource_paths()),
    )
    try:
        lifecycle = executor.revisions.recover(RevisionRecoveryRequest(scenario_id))
    except MicrocycleRevisionStateNotFound:
        lifecycle = executor.revisions.initialise(
            RevisionInitialisationRequest(
                scenario_id,
                f"refs/heads/{request.project.default_ref}",
                request.canonical_development_base,
                (f"scenario-draft:{scenario_id}",),
            )
        )
        return _result(
            ScenarioTransitionKind.REVISION_INITIALISED,
            request,
            lifecycle,
            _outcome(request, scenario_id, "revision_initialised", lifecycle),
        )
    if lifecycle.status == "behavior_complete":
        return _after_behavior_completion(executor, request, draft_state, lifecycle)
    microcycle = await executor.microcycles.advance(
        StrictMicrocycleRequest(
            request.project.project_id,
            _ticket_for(request).production_path,
            Path(request.project.repository_root),
            request.project.binding().with_base_sha(request.canonical_development_base),
            draft_state.approved_microcycle,
            (),
            True,
            executor.revisions,
            binding_request,
        )
    )
    lifecycle = executor.revisions.recover(RevisionRecoveryRequest(scenario_id))
    return _result(
        ScenarioTransitionKind.MICROCYCLE_ADVANCED,
        request,
        lifecycle,
        _outcome(
            request,
            scenario_id,
            microcycle.kind.value,
            lifecycle,
            _evidence(microcycle.state),
            microcycle.blocker_or_replan_reason,
        ),
        reasoning=microcycle.external_reasoning_invoked,
        rack_ai=microcycle.rack_ai_invoked,
    )


def _intent_review_is_pending(state: ScenarioDraftRunState) -> bool:
    return bool(
        state.attempts
        and state.attempts[-1].candidate_revision is not None
        and state.attempts[-1].intent is None
    )


async def _submit_draft(
    executor: StrictFeatureScenarioExecutor,
    request: FeatureScenarioRequest,
    scenario_id: str,
) -> ScenarioAdvanceResult:
    ticket = _ticket_for(request)
    outcome = await executor.drafting.submit_candidate(
        ScenarioDraftRequest(
            scenario_id,
            ticket,
            tuple(request.behavior.source_refs),
            "python",
            "pytest",
            ticket.test_path,
            _facts(Path(request.project.repository_root), request.canonical_development_base, ticket),
            request.canonical_development_base,
        ),
        request.project.binding().with_base_sha(request.canonical_development_base),
    )
    result = _draft_outcome(request, scenario_id, outcome.state.status)
    return _result(
        ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED,
        request,
        None,
        result,
        rack_ai=outcome.submitted_attempt,
    )


async def _review_intent(
    executor: StrictFeatureScenarioExecutor,
    request: FeatureScenarioRequest,
    scenario_id: str,
) -> ScenarioAdvanceResult:
    ticket = _ticket_for(request)
    outcome = await executor.drafting.review_intent(
        ScenarioDraftRequest(
            scenario_id,
            ticket,
            tuple(request.behavior.source_refs),
            "python",
            "pytest",
            ticket.test_path,
            _facts(Path(request.project.repository_root), request.canonical_development_base, ticket),
            request.canonical_development_base,
        )
    )
    approved = outcome.approved
    kind = ScenarioTransitionKind.INTENT_APPROVED if approved else ScenarioTransitionKind.INTENT_REPAIR_REQUIRED
    status = "intent_approved" if approved else "intent_repair_required"
    return _result(kind, request, None, _draft_outcome(request, scenario_id, status), reasoning=True)


def _after_behavior_completion(
    executor: StrictFeatureScenarioExecutor,
    request: FeatureScenarioRequest,
    draft_state: ScenarioDraftRunState,
    lifecycle: MicrocycleRevisionState,
) -> ScenarioAdvanceResult:
    scenario_id = draft_state.scenario_id
    if not draft_state.project_synchronised:
        executor.synchronizer.synchronize(request.project.project_id, lifecycle.canonical_development_base)
        executor.drafting.state_store.save(replace(draft_state, project_synchronised=True))
        return _result(
            ScenarioTransitionKind.PROJECT_SYNCHRONISED,
            request,
            lifecycle,
            _outcome(request, scenario_id, "project_synchronised", lifecycle),
        )
    microcycle = draft_state.approved_microcycle
    if microcycle is None:
        raise ValueError("completed scenario must retain its approved microcycle")
    return _result(
        ScenarioTransitionKind.SCENARIO_COMPLETED,
        request,
        lifecycle,
        _outcome(
            request,
            scenario_id,
            "behavior_complete",
            lifecycle,
            _evidence(microcycle),
        ),
    )


@dataclass(frozen=True)
class StrictFeatureScenarioRunLoop:
    executor: StrictFeatureScenarioExecutor

    async def execute(self, request: FeatureScenarioRequest) -> FeatureScenarioResult:
        for _ in range(MAX_SCENARIO_COMPATIBILITY_TRANSITIONS):
            advanced = await advance(self.executor, request)
            outcome = advanced.result
            if outcome.status == "behavior_complete":
                return outcome
            if outcome.blocked_reason is not None:
                return outcome
        return FeatureScenarioResult(
            request.behavior.ref,
            f"{request.project.project_id}--{request.behavior.ref}",
            "transition_safety_guard_exhausted",
            f"refs/heads/{request.project.default_ref}",
            request.canonical_development_base,
            None,
            None,
            blocked_reason="transition_safety_guard_exhausted",
        )


def _draft_outcome(
    request: FeatureScenarioRequest,
    scenario_id: str,
    status: str,
) -> FeatureScenarioResult:
    return FeatureScenarioResult(
        request.behavior.ref,
        scenario_id,
        status,
        f"refs/heads/{request.project.default_ref}",
        request.canonical_development_base,
        None,
        None,
    )


def _outcome(
    request: FeatureScenarioRequest,
    scenario_id: str,
    status: str,
    lifecycle: MicrocycleRevisionState,
    evidence: tuple[str, ...] = (),
    blocker: str | None = None,
) -> FeatureScenarioResult:
    return FeatureScenarioResult(
        request.behavior.ref,
        scenario_id,
        status,
        lifecycle.canonical_ref,
        lifecycle.canonical_development_base,
        lifecycle.working_ref if lifecycle.status != "behavior_complete" else None,
        lifecycle.working_revision if lifecycle.status != "behavior_complete" else None,
        evidence,
        blocker,
    )


def _result(
    kind: ScenarioTransitionKind,
    request: FeatureScenarioRequest,
    lifecycle: MicrocycleRevisionState | None,
    outcome: FeatureScenarioResult,
    reasoning: bool = False,
    rack_ai: bool = False,
) -> ScenarioAdvanceResult:
    fingerprint = TransitionFingerprint(
        outcome.status,
        request.behavior.ref,
        outcome.scenario_id,
        None,
        outcome.canonical_development_base,
        outcome.working_revision,
        (),
        _next_action(kind, outcome),
    )
    return ScenarioAdvanceResult(
        kind,
        outcome.status,
        outcome.status,
        request.behavior.ref,
        outcome.scenario_id,
        outcome.canonical_ref,
        outcome.canonical_development_base,
        outcome.working_ref,
        outcome.working_revision,
        outcome.evidence_refs,
        reasoning,
        rack_ai,
        outcome.status != "behavior_complete" and outcome.blocked_reason is None,
        outcome.blocked_reason,
        fingerprint,
        outcome,
    )


def _next_action(kind: ScenarioTransitionKind, outcome: FeatureScenarioResult) -> str:
    if outcome.status == "behavior_complete":
        return "complete"
    if kind == ScenarioTransitionKind.DRAFT_CANDIDATE_SUBMITTED:
        return "scenario_intent_review"
    if kind == ScenarioTransitionKind.INTENT_APPROVED:
        return "revision_initialisation"
    if kind == ScenarioTransitionKind.PROJECT_SYNCHRONISED:
        return "scenario_completion"
    return "microcycle_advance"
