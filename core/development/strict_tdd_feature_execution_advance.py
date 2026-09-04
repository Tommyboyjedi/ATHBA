"""One-transition scenario executor beneath the strict-TDD feature application."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from core.development.microcycle_revision_lifecycle import MicrocycleRevisionStateNotFound
from core.development.behavior_contract_surface import DeclaredProductSurface
from core.development.microcycle_revision_state import (
    MicrocycleRevisionState,
    RevisionBindingRequest,
    RevisionInitialisationRequest,
    RevisionRecoveryRequest,
)
from core.development.scenario_drafting_domain import (
    ScenarioDraftRequest,
    ScenarioDraftRunState,
    ScenarioDraftStatus,
)
from core.development.strict_microcycle import StrictMicrocycleRequest
from core.development.strict_tdd_feature_application import FeatureScenarioRequest, FeatureScenarioResult
from core.development.strict_tdd_feature_execution import _evidence, _facts, _ticket_for
from core.development.strict_tdd_transitions import (
    MicrocycleTransitionKind,
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
        if draft_state.status in {"intent_protocol_failure", "scenario_harness_failure"}:
            return _blocked_draft_result(request, scenario_id, draft_state.status)
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
            draft_state=draft_state,
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
            DeclaredProductSurface.compile(request.contract),
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
        regression=microcycle.deterministic_regression_invoked,
        microcycle_kind=microcycle.kind,
        candidate_revision=microcycle.candidate_revision,
        draft_state=draft_state,
        microcycle_fingerprint=microcycle.fingerprint,
    )


def _intent_review_is_pending(state: ScenarioDraftRunState) -> bool:
    return bool(
        state.attempts
        and state.attempts[-1].status in {"candidate_submitted", "intent_review_pending"}
        and state.attempts[-1].candidate_revision is not None
        and state.attempts[-1].intent is None
    )


def _source_requirement_evidence(request: FeatureScenarioRequest):
    clauses = {item.ref: item for item in request.contract.source_clauses}
    missing = [ref for ref in request.behavior.source_refs if ref not in clauses]
    if missing:
        raise ValueError("behavior source refs are absent from the behavior contract")
    return tuple(clauses[ref] for ref in request.behavior.source_refs)

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
            _source_requirement_evidence(request),
            DeclaredProductSurface.compile(request.contract),
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
        draft_state=outcome.state,
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
            _source_requirement_evidence(request),
            DeclaredProductSurface.compile(request.contract),
        )
    )
    status = outcome.state.status
    if status == "intent_protocol_failure":
        return _result(ScenarioTransitionKind.INTENT_PROTOCOL_FAILURE, request, None, _blocked_draft_outcome(request, scenario_id, status), reasoning=True, draft_state=outcome.state)
    if status == "scenario_harness_failure":
        return _result(ScenarioTransitionKind.SCENARIO_HARNESS_FAILURE, request, None, _blocked_draft_outcome(request, scenario_id, status), reasoning=True, draft_state=outcome.state)
    approved = outcome.approved
    kind = ScenarioTransitionKind.INTENT_APPROVED if approved else ScenarioTransitionKind.INTENT_REPAIR_REQUIRED
    result_status = "intent_approved" if approved else "intent_repair_required"
    return _result(kind, request, None, _draft_outcome(request, scenario_id, result_status), reasoning=True, draft_state=outcome.state)


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
            draft_state=replace(draft_state, project_synchronised=True),
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
        draft_state=draft_state,
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


def _blocked_draft_result(
    request: FeatureScenarioRequest,
    scenario_id: str,
    reason: str,
) -> ScenarioAdvanceResult:
    kind = ScenarioTransitionKind.INTENT_PROTOCOL_FAILURE if reason == "intent_protocol_failure" else ScenarioTransitionKind.SCENARIO_HARNESS_FAILURE
    return _result(kind, request, None, _blocked_draft_outcome(request, scenario_id, reason))


def _blocked_draft_outcome(
    request: FeatureScenarioRequest,
    scenario_id: str,
    reason: str,
) -> FeatureScenarioResult:
    return FeatureScenarioResult(
        request.behavior.ref, scenario_id, reason,
        f"refs/heads/{request.project.default_ref}", request.canonical_development_base,
        None, None, blocked_reason=reason,
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
    regression: bool = False,
    microcycle_kind: MicrocycleTransitionKind | None = None,
    candidate_revision: str | None = None,
    draft_state: ScenarioDraftRunState | None = None,
    microcycle_fingerprint: TransitionFingerprint | None = None,
) -> ScenarioAdvanceResult:
    fingerprint = _fingerprint(outcome, request, draft_state, microcycle_fingerprint)
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
        microcycle_kind,
        regression,
        candidate_revision,
    )


def _fingerprint(
    outcome: FeatureScenarioResult,
    request: FeatureScenarioRequest,
    draft_state: ScenarioDraftRunState | None,
    microcycle_fingerprint: TransitionFingerprint | None,
) -> TransitionFingerprint:
    latest = None if draft_state is None or not draft_state.attempts else draft_state.attempts[-1]
    nested = () if microcycle_fingerprint is None else microcycle_fingerprint.retry_counts
    return TransitionFingerprint(
        outcome.status,
        request.behavior.ref if microcycle_fingerprint is None else microcycle_fingerprint.behavior_ref,
        outcome.scenario_id if microcycle_fingerprint is None else microcycle_fingerprint.scenario_id,
        None if microcycle_fingerprint is None else microcycle_fingerprint.frontier_index,
        outcome.canonical_development_base if microcycle_fingerprint is None else microcycle_fingerprint.canonical_sha,
        outcome.working_revision or (None if latest is None else latest.candidate_revision) or (None if microcycle_fingerprint is None else microcycle_fingerprint.working_sha),
        (() if draft_state is None else (len(draft_state.attempts),)) + nested,
        _pending_action(draft_state, outcome, microcycle_fingerprint),
    )


def _pending_action(
    draft_state: ScenarioDraftRunState | None,
    outcome: FeatureScenarioResult,
    microcycle_fingerprint: TransitionFingerprint | None,
) -> str:
    if outcome.status == "behavior_complete":
        return "complete"
    if draft_state is None:
        return "blocked" if outcome.blocked_reason is not None else "scenario_advance"
    if draft_state.status in {
        ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value,
        ScenarioDraftStatus.INTENT_PROTOCOL_FAILURE.value,
        ScenarioDraftStatus.SCENARIO_HARNESS_FAILURE.value,
    }:
        return "blocked"
    if draft_state.approved_microcycle is not None:
        return "revision_initialisation" if microcycle_fingerprint is None else microcycle_fingerprint.pending_action
    if not draft_state.attempts or draft_state.attempts[-1].candidate_revision is None:
        return "scenario_draft_submission"
    if draft_state.attempts[-1].intent is None:
        return "scenario_intent_review"
    return "scenario_draft_repair"
