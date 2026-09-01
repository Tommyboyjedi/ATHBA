"""One-persisted-transition feature application and its compatibility loop."""
from __future__ import annotations

from dataclasses import replace

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.project_environment import DevelopmentProject
from core.development.behavior_contract_coordinator import ContractPlanningRequest
from core.development.specification_assessment import GatekeeperStateRequest
from core.development.strict_tdd_feature_application import (
    FeatureReconciliationRequest,
    FeatureScenarioRequest,
    StrictTddFeatureApplicationService,
    _result,
)
from core.development.strict_tdd_feature_domain import (
    CompletedBehaviorReference,
    StrictTddFeatureRequest,
    StrictTddFeatureState,
    StrictTddFeatureStatus,
)
from core.development.strict_tdd_transitions import (
    FeatureAdvanceResult,
    FeatureTransitionKind,
    TransitionFingerprint,
)

MAX_FEATURE_COMPATIBILITY_TRANSITIONS = 100


async def advance(
    service: StrictTddFeatureApplicationService,
    request: StrictTddFeatureRequest,
) -> FeatureAdvanceResult:
    project = service.environment.create_or_load_python_project(request.project_id)
    state = service.states.load(request.project_id)
    if state is None:
        state = StrictTddFeatureState(
            request.project_id,
            request.source_requirement_hash,
            StrictTddFeatureStatus.PLANNING.value,
            canonical_ref=f"refs/heads/{project.default_ref}",
            canonical_development_base=project.trusted_base_sha,
        )
        service.states.save(state)
        return _result_for(FeatureTransitionKind.PROJECT_LOADED, state, project)
    if state.status == StrictTddFeatureStatus.PLANNING.value and state.contract_payload is None:
        return await _persist_contract(service, request, project)
    if state.status == StrictTddFeatureStatus.PLANNING.value:
        return await _persist_checklist(service, state, project)
    if state.status == StrictTddFeatureStatus.COMPLETED.value:
        return _result_for(FeatureTransitionKind.FEATURE_COMPLETED, state, project)
    if state.status == StrictTddFeatureStatus.BLOCKED.value:
        return _result_for(FeatureTransitionKind.BLOCKED, state, project, state.blocked_reason)
    if state.pending_completed_behavior is not None:
        return _record_completed_behavior(service, state, project)
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}), load_options=None)
    behavior = _next_behavior(state, contract)
    if state.current_scenario_id is not None and behavior is not None:
        return await _advance_scenario(service, state, project, behavior)
    if behavior is not None:
        return _select_behavior(service, state, project, behavior.ref)
    if not state.final_reconciliation:
        return await _reconcile(service, state, project, contract)
    completed = replace(state, status=StrictTddFeatureStatus.COMPLETED.value)
    service.states.save(completed)
    return _result_for(FeatureTransitionKind.FEATURE_COMPLETED, completed, project)


async def _persist_contract(
    service: StrictTddFeatureApplicationService,
    request: StrictTddFeatureRequest,
    project: DevelopmentProject,
) -> FeatureAdvanceResult:
    contract = await service.contract_planner.create_contract(
        ContractPlanningRequest(
            request.project_id,
            request.source_requirement,
            list(request.production_paths),
            list(request.test_paths),
        )
    )
    state = StrictTddFeatureState(
        request.project_id,
        request.source_requirement_hash,
        StrictTddFeatureStatus.PLANNING.value,
        contract.to_dict(),
        canonical_ref=f"refs/heads/{project.default_ref}",
        canonical_development_base=project.trusted_base_sha,
    )
    service.states.save(state)
    return _result_for(FeatureTransitionKind.CONTRACT_PERSISTED, state, project, reasoning=True)


async def _persist_checklist(
    service: StrictTddFeatureApplicationService,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
) -> FeatureAdvanceResult:
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}), load_options=None)
    checklist = await service.gatekeeper.ensure_state(GatekeeperStateRequest(contract, None))
    updated = replace(
        state,
        status=StrictTddFeatureStatus.RUNNING.value,
        gatekeeper_payload=checklist.to_dict(),
    )
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.GATEKEEPER_PERSISTED, updated, project, reasoning=True)


def _select_behavior(
    service: StrictTddFeatureApplicationService,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
    behavior_ref: str,
) -> FeatureAdvanceResult:
    scenario_id = f"{state.project_id}--{behavior_ref}"
    selected = replace(state, current_scenario_id=scenario_id)
    service.states.save(selected)
    return _result_for(FeatureTransitionKind.BEHAVIOR_SELECTED, selected, project, behavior_ref=behavior_ref)


async def _reconcile(
    service: StrictTddFeatureApplicationService,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
    contract: BehaviorContract,
) -> FeatureAdvanceResult:
    reconciliation = await service.reconciler.reconcile(
        FeatureReconciliationRequest(
            contract,
            state.completed_behaviors,
            dict(state.gatekeeper_payload or {}),
            str(state.canonical_development_base),
        )
    )
    updated = replace(state, final_reconciliation=reconciliation)
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.RECONCILIATION_COMPLETED, updated, project, reasoning=True)


def _next_behavior(state: StrictTddFeatureState, contract: BehaviorContract):
    completed = {item.behavior_ref for item in state.completed_behaviors}
    if state.current_scenario_id is not None:
        return _behavior_for_scenario(contract, state.current_scenario_id)
    for behavior in contract.observable_requirements:
        if behavior.ref not in completed:
            return behavior
    return None


def _behavior_for_scenario(contract: BehaviorContract, scenario_id: str):
    for behavior in contract.observable_requirements:
        if scenario_id.endswith(f"--{behavior.ref}"):
            return behavior
    raise ValueError("persisted feature scenario does not match the behavior contract")


async def _advance_scenario(
    service: StrictTddFeatureApplicationService,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
    behavior: BehaviorContractRequirement,
) -> FeatureAdvanceResult:
    request = FeatureScenarioRequest(
        project,
        BehaviorContract.from_dict(dict(state.contract_payload or {}), load_options=None),
        behavior,
        state.canonical_development_base or project.trusted_base_sha,
    )
    advanced = await service.scenarios.advance(request)
    outcome = advanced.result
    if outcome.status == "behavior_complete":
        pending = CompletedBehaviorReference(
            outcome.behavior_ref,
            outcome.scenario_id,
            outcome.canonical_development_base,
            outcome.evidence_refs,
        )
        updated = replace(
            state,
            canonical_ref=outcome.canonical_ref,
            canonical_development_base=outcome.canonical_development_base,
            working_ref=None,
            working_revision=None,
            pending_completed_behavior=pending,
            evidence_refs=(*state.evidence_refs, *outcome.evidence_refs),
        )
        service.states.save(updated)
        return _result_for(FeatureTransitionKind.SCENARIO_ADVANCED, updated, project, behavior_ref=behavior.ref)
    if outcome.blocked_reason is not None or outcome.status in {"scenario_draft_blocked", "replan_required", "attempts_exhausted", "blocked"}:
        updated = service._after_scenario(state, outcome)
        service.states.save(updated)
        return _result_for(FeatureTransitionKind.BLOCKED, updated, project, updated.blocked_reason, behavior.ref)
    return _result_for(FeatureTransitionKind.SCENARIO_ADVANCED, state, project, behavior_ref=behavior.ref)


def _record_completed_behavior(
    service: StrictTddFeatureApplicationService,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
) -> FeatureAdvanceResult:
    completed = state.pending_completed_behavior
    if completed is None:
        raise ValueError("behavior recording requires a pending completed behavior")
    updated = replace(
        state,
        current_scenario_id=None,
        pending_completed_behavior=None,
        completed_behaviors=(*state.completed_behaviors, completed),
    )
    service.states.save(updated)
    return _result_for(
        FeatureTransitionKind.BEHAVIOR_RECORDED,
        updated,
        project,
        behavior_ref=completed.behavior_ref,
    )


class StrictTddFeatureRunLoop:
    """Runs legacy callers through the same advance state machine."""

    def __init__(self, service: StrictTddFeatureApplicationService):
        self.service = service

    async def run(self, request: StrictTddFeatureRequest):
        for _ in range(MAX_FEATURE_COMPATIBILITY_TRANSITIONS):
            advanced = await self.service.advance(request)
            if advanced.kind == FeatureTransitionKind.FEATURE_COMPLETED:
                return advanced.result
            if advanced.kind == FeatureTransitionKind.BLOCKED:
                return advanced.result
        state = self.service.states.load(request.project_id)
        if state is None:
            raise RuntimeError("feature compatibility loop did not persist state")
        project = self.service.environment.create_or_load_python_project(request.project_id)
        blocked = replace(state, status=StrictTddFeatureStatus.BLOCKED.value, blocked_reason="transition_safety_guard_exhausted")
        self.service.states.save(blocked)
        return _result(project, blocked)


def _result_for(
    kind: FeatureTransitionKind,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
    blocker: str | None = None,
    behavior_ref: str | None = None,
    reasoning: bool = False,
) -> FeatureAdvanceResult:
    fingerprint = TransitionFingerprint(
        state.status,
        behavior_ref,
        state.current_scenario_id,
        None,
        state.canonical_development_base,
        state.working_revision,
        (len(state.completed_behaviors),),
        _pending_action(state),
    )
    return FeatureAdvanceResult(
        kind,
        state.status,
        state.status,
        state.project_id,
        behavior_ref,
        state.current_scenario_id,
        state.canonical_ref,
        state.canonical_development_base,
        state.working_ref,
        state.working_revision,
        state.evidence_refs,
        reasoning,
        False,
        False,
        kind not in {FeatureTransitionKind.FEATURE_COMPLETED, FeatureTransitionKind.BLOCKED},
        blocker,
        fingerprint,
        _result(project, state),
    )


def _pending_action(state: StrictTddFeatureState) -> str:
    if state.status == StrictTddFeatureStatus.PLANNING.value:
        return "gatekeeper_checklist"
    if state.current_scenario_id is not None:
        return "scenario_advance"
    if not state.final_reconciliation:
        return "reconciliation"
    return "feature_completion"
