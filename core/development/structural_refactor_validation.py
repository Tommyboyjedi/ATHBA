"""Validate accepted behaviour before rerunning or promoting structural work."""
from __future__ import annotations

import json
from dataclasses import replace

from core.development.deterministic_regression import DeterministicRegressionRequest, REGRESSION_CLEAR
from core.development.microcycle_domain import BoundaryClassificationRequest, BoundaryOutcome, FrontierExecutionRequest, MicrocycleState
from core.development.structural_refactor_context import StructuralContext, replace_attempt, evidence
from core.development.structural_refactor_domain import StructuralPhase


def validate(context: StructuralContext) -> MicrocycleState:
    state = context.state
    attempt = state.structural_attempts[-1]
    revision = attempt.candidate_revision
    if revision is None:
        raise ValueError("structural validation requires candidate revision")
    candidate = context.materialise(revision, previous=True)
    try:
        regression = context.service.regression.run(DeterministicRegressionRequest(
            candidate.project_root, state.regression.command, state.model.canonical_test_identity,
            context.request.prior_completed_test_nodes, True,
        )).state(state.regression.command)
    finally:
        context.service.candidates.cleanup(candidate)
    updated = replace(state, structural_regression=regression)
    refs = (*attempt.evidence_refs, json.dumps(regression.to_dict(), sort_keys=True))
    if regression.status != REGRESSION_CLEAR:
        return replace_attempt(updated, phase=StructuralPhase.REJECTED, evidence_refs=refs,
                               reason="structural_accepted_regression_failed")
    if not context.candidate_in_scope(revision):
        return replace_attempt(updated, phase=StructuralPhase.REJECTED, evidence_refs=refs,
                               reason="structural_candidate_outside_problem")
    return replace_attempt(updated, phase=StructuralPhase.RERUN, evidence_refs=refs)


def rerun(context: StructuralContext) -> MicrocycleState:
    state = context.state
    attempt = state.structural_attempts[-1]
    if attempt.candidate_revision is None:
        raise ValueError("structural rerun requires candidate revision")
    candidate = context.materialise(attempt.candidate_revision)
    try:
        diagnostic = context.adapter.execute_frontier(FrontierExecutionRequest(
            candidate.artifact, str(candidate.project_root), state.model.test_path,
            context.request.production_path,
        ))
        observation = context.adapter.classify_boundary(BoundaryClassificationRequest(
            diagnostic, candidate.artifact, state.fragments[state.frontier.index], BoundaryOutcome.GREEN.value,
        ))
    finally:
        context.service.candidates.cleanup(candidate)
    updated = replace(state, structural_rerun=observation,
                      boundary_evidence=(*state.boundary_evidence, observation))
    refs = (*attempt.evidence_refs, evidence(observation))
    allowed = {BoundaryOutcome.GREEN.value, BoundaryOutcome.VALID_BEHAVIORAL_RED.value,
               BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value}
    if observation.outcome in allowed:
        return replace_attempt(updated, phase=StructuralPhase.PROMOTING, evidence_refs=refs)
    return replace_attempt(updated, phase=StructuralPhase.REJECTED, evidence_refs=refs,
                           reason=observation.outcome)
