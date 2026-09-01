"""One-transition scenario executor beneath the strict-TDD feature application."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.development.microcycle_revision_state import (
    RevisionBindingRequest,
    RevisionInitialisationRequest,
    RevisionRecoveryRequest,
)
from core.development.scenario_drafting_domain import ScenarioDraftRequest
from core.development.strict_microcycle import StrictMicrocycleRequest
from core.development.strict_tdd_feature_application import FeatureScenarioRequest, FeatureScenarioResult
from core.development.strict_tdd_feature_execution import _evidence, _facts, _ticket_for
from core.development.strict_tdd_transitions import (
    ScenarioAdvanceResult,
    ScenarioTransitionKind,
    TransitionFingerprint,
)

MAX_SCENARIO_COMPATIBILITY_TRANSITIONS = 100


async def advance(executor: object, request: FeatureScenarioRequest) -> ScenarioAdvanceResult:
    scenario_id = f"{request.project.project_id}--{request.behavior.ref}"
    draft_state = executor.drafting.state_store.load(scenario_id)
    if draft_state is None or draft_state.approved_microcycle is None:
        return await _draft(executor, request, scenario_id)
    binding_request = RevisionBindingRequest(
        scenario_id,
        request.project.project_id,
        request.project.repository_root,
        tuple(request.project.runtime.resource_paths()),
    )
    try:
        lifecycle = executor.revisions.recover(RevisionRecoveryRequest(scenario_id))
    except ValueError:
        executor.revisions.initialise(
            RevisionInitialisationRequest(
                scenario_id,
                f"refs/heads/{request.project.default_ref}",
                request.canonical_development_base,
                (f"scenario-draft:{scenario_id}",),
            )
        )
        lifecycle = executor.revisions.recover(RevisionRecoveryRequest(scenario_id))
        return _result(
            ScenarioTransitionKind.REVISION_INITIALISED,
            request,
            lifecycle,
            FeatureScenarioResult(
                request.behavior.ref,
                scenario_id,
                "revision_initialised",
                lifecycle.canonical_ref,
                lifecycle.canonical_development_base,
                lifecycle.working_ref,
                lifecycle.working_revision,
            ),
        )
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
    if microcycle.kind.value == "behavior_completed":
        executor.synchronizer.synchronize(request.project.project_id, lifecycle.canonical_development_base)
        outcome = FeatureScenarioResult(
            request.behavior.ref,
            scenario_id,
            "behavior_complete",
            lifecycle.canonical_ref,
            lifecycle.canonical_development_base,
            None,
            None,
            _evidence(microcycle.state),
        )
        return _result(ScenarioTransitionKind.SCENARIO_COMPLETED, request, lifecycle, outcome)
    outcome = FeatureScenarioResult(
        request.behavior.ref,
        scenario_id,
        microcycle.kind.value,
        lifecycle.canonical_ref,
        lifecycle.canonical_development_base,
        lifecycle.working_ref,
        lifecycle.working_revision,
        _evidence(microcycle.state),
        microcycle.blocker_or_replan_reason,
    )
    return _result(
        ScenarioTransitionKind.MICROCYCLE_ADVANCED,
        request,
        lifecycle,
        outcome,
        reasoning=microcycle.external_reasoning_invoked,
        rack_ai=microcycle.rack_ai_invoked,
    )


async def _draft(executor: object, request: FeatureScenarioRequest, scenario_id: str) -> ScenarioAdvanceResult:
    ticket = _ticket_for(request)
    outcome = await executor.drafting.draft(
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
    status = "intent_approved" if outcome.approved else "scenario_draft_blocked"
    result = FeatureScenarioResult(
        request.behavior.ref,
        scenario_id,
        status,
        f"refs/heads/{request.project.default_ref}",
        request.canonical_development_base,
        None,
        None,
        blocked_reason=None if outcome.approved else outcome.state.status,
    )
    kind = ScenarioTransitionKind.INTENT_APPROVED if outcome.approved else ScenarioTransitionKind.DRAFT_ATTEMPTED
    return _draft_result(kind, request, result, rack_ai=outcome.submitted_attempt)


@dataclass(frozen=True)
class StrictFeatureScenarioRunLoop:
    executor: object

    async def execute(self, request: FeatureScenarioRequest) -> FeatureScenarioResult:
        for _ in range(MAX_SCENARIO_COMPATIBILITY_TRANSITIONS):
            advanced = await advance(self.executor, request)
            outcome = advanced.result
            if outcome.status == "behavior_complete":
                return outcome
            if outcome.status in {"scenario_draft_blocked", "blocked", "replan_required", "attempts_exhausted"}:
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


def _result(
    kind: ScenarioTransitionKind,
    request: FeatureScenarioRequest,
    lifecycle: object,
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
        "microcycle_advance",
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


def _draft_result(
    kind: ScenarioTransitionKind,
    request: FeatureScenarioRequest,
    outcome: FeatureScenarioResult,
    rack_ai: bool,
) -> ScenarioAdvanceResult:
    fingerprint = TransitionFingerprint(
        outcome.status,
        request.behavior.ref,
        outcome.scenario_id,
        None,
        outcome.canonical_development_base,
        None,
        (),
        "revision_initialisation" if outcome.status == "intent_approved" else "scenario_draft",
    )
    return ScenarioAdvanceResult(
        kind,
        "drafting",
        outcome.status,
        request.behavior.ref,
        outcome.scenario_id,
        outcome.canonical_ref,
        outcome.canonical_development_base,
        None,
        None,
        (),
        outcome.status == "intent_approved",
        rack_ai,
        outcome.blocked_reason is None,
        outcome.blocked_reason,
        fingerprint,
        outcome,
    )
