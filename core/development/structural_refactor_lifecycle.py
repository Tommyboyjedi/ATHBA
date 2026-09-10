"""Bounded checkpointed structural recovery inside behavioural TDD."""
from __future__ import annotations

from dataclasses import replace

from core.development.microcycle_domain import BoundaryOutcome, MicrocyclePendingAction, MicrocycleState, RegressionState
from core.development.deterministic_regression import REGRESSION_CLEAR
from core.development.microcycle_revision_state import RevisionTransitionKind
from core.development.strict_microcycle import _advance_working_revision, _promote_canonical_revision, _working_binding
from core.development.structural_refactor_context import StructuralContext, replace_attempt
from core.development.structural_refactor_domain import StructuralAttempt, StructuralPhase, StructuralRefactorPolicy, StructuralProductionSource
from core.development.structural_refactor_validation import validate, rerun
from core.development.structural_refactor_work import StructuralWorkFactory, StructuralWorkInput
from core.development.strict_tdd_transitions import MicrocycleTransitionKind, MicrocycleAdvanceResult


class StructuralRefactorLifecycle:
    """Dispatch one durable action; unknown in-flight submissions fail closed."""

    def __init__(self, policy: StructuralRefactorPolicy = StructuralRefactorPolicy()):
        self.policy = policy

    async def advance(self, context: StructuralContext) -> MicrocycleAdvanceResult:
        from core.development.strict_microcycle_advance import _result, _status
        state = context.state
        attempts = tuple(item for item in state.structural_attempts if item.frontier_index == state.frontier.index)
        phase = attempts[-1].phase if attempts else StructuralPhase.PENDING
        invoked = False
        kind = MicrocycleTransitionKind.STRUCTURAL_REFACTOR_ADVANCED
        blocker = None
        if phase == StructuralPhase.STARTED:
            updated = replace_attempt(state, phase=StructuralPhase.BLOCKED,
                                      reason="structural_refactor_interrupted_submission")
            blocker = "structural_refactor_interrupted_submission"
        elif phase in {StructuralPhase.PENDING, StructuralPhase.REJECTED}:
            if len(attempts) >= self.policy.max_attempts:
                updated = state
                blocker = "structural_refactor_attempts_exhausted"
            else:
                updated = await self.submit(context, len(attempts) + 1)
                invoked = True
        elif phase == StructuralPhase.VALIDATING:
            updated = validate(context)
        elif phase == StructuralPhase.RERUN:
            updated = rerun(context)
        elif phase == StructuralPhase.PROMOTING:
            updated = promote(context)
            kind = MicrocycleTransitionKind.STRUCTURAL_REFACTOR_PROMOTED
        elif phase == StructuralPhase.PROMOTED:
            # Defensive restart projection: never issue another model call.
            updated = replace(state, pending_action=MicrocyclePendingAction.OBSERVE_FRONTIER.value)
        else:
            updated = state
            blocker = attempts[-1].reason or "structural_refactor_blocked"
        if blocker:
            updated = replace(updated, pending_action=MicrocyclePendingAction.BLOCKED.value)
            kind = MicrocycleTransitionKind.BLOCKED
        context.service.state_store.save(updated)
        return _result(kind, _status(state), updated, context.request,
                       rack_ai=invoked, regression=phase == StructuralPhase.VALIDATING, blocker=blocker)

    async def submit(self, context: StructuralContext, number: int) -> MicrocycleState:
        state, request = context.state, context.request
        base = state.development_base_revision
        if state.candidate_chain_revision not in (None, base):
            raise ValueError("structural refactoring requires a trusted accepted prefix")
        problem = context.problem()
        commands = (state.regression.command, *(
            (*state.regression.command, node) for node in request.prior_completed_test_nodes
        ))
        work = StructuralWorkFactory(self.policy).build(StructuralWorkInput(
            request.project_id, state.model.scenario_id, state.frontier.index, number,
            base, problem, context.adapter.focus_structural_production(StructuralProductionSource(problem, context.source(base))), commands,
        ))
        attempt = StructuralAttempt(work.id, state.frontier.index, base)
        started = replace(state, structural_attempts=(*state.structural_attempts, attempt),
                          structural_regression=None, structural_rerun=None)
        context.service.state_store.save(started)
        binding = replace(_working_binding(request, base), environment_resources=[])
        result = await context.service.gateway.execute(work, binding)
        refs = tuple(item for item in (result.evidence_location, result.error) if item)
        if result.work_unit_id != work.id:
            return replace_attempt(started, phase=StructuralPhase.BLOCKED,
                                   reason="structural_refactor_submission_mismatch", evidence_refs=refs)
        phase = StructuralPhase.VALIDATING if result.accepted and result.accepted_revision else StructuralPhase.REJECTED
        return replace_attempt(started, phase=phase, candidate_revision=result.accepted_revision,
                               evidence_refs=refs, reason=result.status)


def promote(context: StructuralContext) -> MicrocycleState:
    state = context.state
    attempt = state.structural_attempts[-1]
    revision = attempt.candidate_revision
    if revision is None or state.structural_regression is None or state.structural_regression.status != REGRESSION_CLEAR:
        raise ValueError("structural promotion requires accepted regression proof")
    if state.structural_rerun is None or state.structural_rerun.outcome not in {
        BoundaryOutcome.GREEN.value, BoundaryOutcome.VALID_BEHAVIORAL_RED.value,
        BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value,
    }:
        raise ValueError("structural promotion requires a supported frontier rerun")
    _advance_working_revision(context.request, revision, RevisionTransitionKind.STRUCTURAL_REFACTOR_PROMOTED.value, attempt.identity)
    _promote_canonical_revision(context.request, revision, attempt.identity)
    return replace(replace_attempt(state, phase=StructuralPhase.PROMOTED, reason="returned_to_normal_tdd"),
                   development_base_revision=revision, candidate_chain_revision=revision,
                   current_accepted_red_revision=None,
                   regression=RegressionState("pending", state.regression.command),
                   pending_action=MicrocyclePendingAction.OBSERVE_FRONTIER.value)
