"""Durable replacement transitions before ordinary exhausted-behavior splitting."""
from __future__ import annotations

from dataclasses import replace

from core.development.behavior_contract_domain import BehaviorContract
from core.development.behavior_requirement_repair import validate_response
from core.development.behavior_requirement_repair_domain import (
    BehaviorRepairBlocker, BehaviorRepairFailure, BehaviorRepairFeedback, BehaviorRepairPhase,
    BehaviorRepairRecord, BehaviorRepairRequest,
)
from core.development.microcycle_domain import IntentStatus
from core.development.scenario_drafting_domain import (
    MAX_TESTER_SCENARIO_ATTEMPTS, ScenarioDraftRunState, ScenarioDraftStatus,
)
from core.development.strict_tdd_feature_domain import StrictTddFeatureState, StrictTddFeatureStatus
from core.development.strict_tdd_feature_replan import FeatureReplanContext
from core.development.strict_tdd_transitions import FeatureTransitionKind


def require_repair(state: StrictTddFeatureState, draft: ScenarioDraftRunState) -> StrictTddFeatureState | None:
    if (draft.status != ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
            or draft.approved_microcycle is not None or draft.harness_failure_evidence is not None
            or tuple(item.attempt_number for item in draft.attempts) != tuple(range(1, MAX_TESTER_SCENARIO_ATTEMPTS + 1))
            or any(item.request.original.ref == draft.behavior_ref for item in state.behavior_repairs)):
        return None
    feedback = tuple(
        BehaviorRepairFeedback(item.attempt_number, item.intent.rationale)
        for item in draft.attempts
        if item.intent is not None and item.intent.status == IntentStatus.WRONG_BEHAVIOR.value
        and item.intent.scenario_id == draft.scenario_id and item.intent_protocol_failure is None
    )
    if not feedback:
        return None
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    original = next(item for item in contract.observable_requirements if item.ref == draft.behavior_ref)
    clauses = {item.ref: item for item in contract.source_clauses}
    if (draft.scenario_id != state.current_scenario_id
            or draft.development_base_revision != state.canonical_development_base
            or tuple(original.source_refs) != draft.source_requirement_refs
            or any(item.behavior_ref == original.ref for item in state.completed_behaviors)
            or state.pending_completed_behavior is not None
            or state.working_revision is not None):
        raise ValueError("repair draft differs from unresolved trusted feature identity")
    request = BehaviorRepairRequest(
        state.project_id, original, tuple(clauses[ref] for ref in original.source_refs), feedback,
        draft.scenario_id, str(state.canonical_ref), str(state.canonical_development_base),
    )
    return replace(state, behavior_repairs=(*state.behavior_repairs, BehaviorRepairRecord(request)),
                   evidence_refs=(*state.evidence_refs, f"scenario-draft:{draft.scenario_id}"))


def repair_pending(state: StrictTddFeatureState) -> bool:
    return bool(state.behavior_repairs and state.behavior_repairs[-1].phase in {
        BehaviorRepairPhase.REQUIRED, BehaviorRepairPhase.STARTED, BehaviorRepairPhase.RECEIVED,
    })


def selected_scenario_id(state: StrictTddFeatureState, behavior_ref: str) -> str:
    repaired = any(item.request.original.ref == behavior_ref and item.phase == BehaviorRepairPhase.APPLIED
                   for item in state.behavior_repairs)
    generation = "--repair-1" if repaired else ""
    return f"{state.project_id}{generation}--{behavior_ref}"


async def advance_repair(service, context: FeatureReplanContext):
    from core.development.strict_tdd_feature_application_advance import _result_for

    state, project = context.state, context.project
    record = state.behavior_repairs[-1]
    invoked = False
    try:
        if record.phase == BehaviorRepairPhase.STARTED:
            raise BehaviorRepairFailure(BehaviorRepairBlocker.INTERRUPTED,
                                       "Repair submission has no durable response; no resubmission.")
        _validate_identity(state, record)
        if record.phase == BehaviorRepairPhase.REQUIRED:
            record = replace(record, phase=BehaviorRepairPhase.STARTED)
            service.states.save(_with_record(state, record))
            invoked = True
            raw = await service.contract_planner.repair_requirement(record.request)
            record = replace(record, phase=BehaviorRepairPhase.RECEIVED, raw_response=raw)
            updated = _with_record(state, record)
            kind = FeatureTransitionKind.BEHAVIOR_REPAIR_RECEIVED
        else:
            record = validate_response(record)
            contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
            requirements = [record.repaired if item.ref == record.request.original.ref else item
                            for item in contract.observable_requirements]
            record = replace(record, phase=BehaviorRepairPhase.APPLIED)
            updated = replace(_with_record(state, record), current_scenario_id=None,
                              contract_payload=replace(contract, observable_requirements=requirements).to_dict())
            kind = FeatureTransitionKind.BEHAVIOR_REPAIR_APPLIED
    except BehaviorRepairFailure as error:
        record = replace(record, phase=BehaviorRepairPhase.FAILED, blocker=error.kind, detail=error.detail)
        updated = replace(_with_record(state, record), status=StrictTddFeatureStatus.BLOCKED.value,
                          blocked_reason=error.kind.value)
        kind = FeatureTransitionKind.BLOCKED
    service.states.save(updated)
    return _result_for(kind, updated, project, updated.blocked_reason,
                       record.request.original.ref, reasoning=invoked)


def _with_record(state: StrictTddFeatureState, record: BehaviorRepairRecord) -> StrictTddFeatureState:
    return replace(state, behavior_repairs=(*state.behavior_repairs[:-1], record))


def _validate_identity(state: StrictTddFeatureState, record: BehaviorRepairRecord) -> None:
    try:
        contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    except (ValueError, TypeError, KeyError) as error:
        raise BehaviorRepairFailure(BehaviorRepairBlocker.INCOMPATIBLE,
                                   "Persisted contract no longer resolves the repair identity") from error
    request = record.request
    clauses = {item.ref: item for item in contract.source_clauses}
    active = {item.ref: item for item in contract.observable_requirements}
    if (state.project_id != request.project_id or active.get(request.original.ref) != request.original
            or state.current_scenario_id != request.scenario_id
            or state.canonical_ref != request.canonical_ref
            or state.canonical_development_base != request.canonical_revision
            or tuple(clauses.get(ref) for ref in request.original.source_refs) != request.source_clauses
            or any(item.behavior_ref == request.original.ref for item in state.completed_behaviors)
            or state.pending_completed_behavior is not None or state.working_revision is not None
            or sum(item.request.original.ref == request.original.ref for item in state.behavior_repairs) != 1):
        raise BehaviorRepairFailure(BehaviorRepairBlocker.INCOMPATIBLE,
                                   "Behavior, source clauses or trusted feature identity changed during repair")
