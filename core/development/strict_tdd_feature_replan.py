"""Persisted feature transitions for exhausted-parent recovery."""
from __future__ import annotations
from core.execution.rack_ai_runtime import RackAiResourceWait
from core.execution.provider_reasoning_gateway import wait_for_reasoning

from dataclasses import dataclass, replace

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.behavior_replan_domain import (
    BehavioralFailure, BehaviorReplanBlocker, BehaviorReplanCorrectionRequest, BehaviorReplanDisposition,
    BehaviorReplanPhase, BehaviorReplanRecord, BehaviorReplanRequest,
)
from core.development.behavior_replan_validation import BehaviorSplitValidationContext, validate_split
from core.development.behavior_replanning import BehaviorReplanFailure
from core.development.project_environment import DevelopmentProject
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService
from core.development.strict_tdd_feature_domain import StrictTddFeatureState, StrictTddFeatureStatus
from core.development.strict_tdd_transitions import FeatureTransitionKind


@dataclass(frozen=True)
class FeatureReplanContext:
    state: StrictTddFeatureState
    project: DevelopmentProject


def require_replan(state: StrictTddFeatureState, failure: BehavioralFailure) -> StrictTddFeatureState:
    """The sole admission path for a valid obligation whose delivery failed."""
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    parent = next(item for item in contract.observable_requirements if item.ref == failure.behavior_ref)
    if parent.ref in {item.behavior_ref for item in state.completed_behaviors}:
        raise ValueError("completed behavior cannot be replanned")
    if any(parent.ref in item.depends_on for item in contract.observable_requirements
           if item.ref in {done.behavior_ref for done in state.completed_behaviors}):
        raise ValueError("completed behavior depends on an unresolved parent")
    if any(item.request.parent.ref == parent.ref for item in state.behavior_replans):
        raise ValueError("parent already has durable replan evidence")
    lineage = next(((*item.request.lineage, item.request.parent.ref)
                    for item in state.behavior_replans if parent.ref in item.child_refs), ())
    request = BehaviorReplanRequest(
        state.project_id, parent,
        tuple(item for item in contract.source_clauses if item.ref in parent.source_refs),
        str(state.canonical_ref), str(state.canonical_development_base), failure.summary,
        failure.evidence_refs, lineage,
    )
    return replace(state, behavior_replans=(*state.behavior_replans, BehaviorReplanRecord(request)),
                   evidence_refs=(*state.evidence_refs, f"feature:{state.project_id}:behavior-replan:{parent.ref}"))


def replan_pending(state: StrictTddFeatureState) -> bool:
    return bool(state.behavior_replans and state.behavior_replans[-1].phase in {
        BehaviorReplanPhase.REQUIRED, BehaviorReplanPhase.STARTED, BehaviorReplanPhase.RECEIVED,
        BehaviorReplanPhase.CORRECTION_STARTED,
    })


async def advance_replan(
    service: StrictTddFeatureApplicationService,
    context: FeatureReplanContext,
):
    from core.development.strict_tdd_feature_application_advance import _result_for

    state, project = context.state, context.project
    record = state.behavior_replans[-1]
    phase = record.phase
    if phase == BehaviorReplanPhase.STARTED:
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.INTERRUPTED,
                      detail="Planner submission has no durable response; human reconciliation required, no resubmission."))
    if phase == BehaviorReplanPhase.CORRECTION_STARTED:
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.INTERRUPTED,
                      detail="Planner correction submission has no durable response; human reconciliation required, no resubmission."))
    if phase == BehaviorReplanPhase.REQUIRED:
        if len(state.behavior_replans) > service.replan_policy.max_splits:
            return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.BUDGET_EXHAUSTED,
                          detail="Configured total split safety budget reached; human escalation required."))
        await wait_for_reasoning(service.contract_planner.gateway)
        started = replace(record, phase=BehaviorReplanPhase.STARTED)
        service.states.save(_with_record(state, started))
        try:
            response = await service.contract_planner.replan_requirement(record.request)
        except RackAiResourceWait:
            service.states.save(state)
            raise
        except BehaviorReplanFailure as error:
            if error.kind == BehaviorReplanBlocker.PROTOCOL_FAILURE and error.raw_response is not None:
                return await _correct_invalid_split(service, context, state, project,
                    replace(started, rejected_response=error.raw_response), error.detail, format_only=True)
            return _block(service, context, replace(started, blocker=error.kind, detail=error.detail,
                                                   rejected_response=error.raw_response))
        received = replace(started, phase=BehaviorReplanPhase.RECEIVED, response=response)
        updated = _with_record(state, received)
        service.states.save(updated)
        return _result_for(FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED, updated, project,
                           behavior_ref=record.request.parent.ref, reasoning=True)
    if record.response is None:
        raise ValueError("received replan has no response")
    if record.response.disposition != BehaviorReplanDisposition.SPLIT:
        blocker = (BehaviorReplanBlocker.SOURCE_AUTHORITY_INSUFFICIENT
                   if record.response.disposition == BehaviorReplanDisposition.SOURCE_AUTHORITY_INSUFFICIENT
                   else BehaviorReplanBlocker.NOT_PRODUCED)
        return _block(service, context, replace(record, blocker=blocker,
            detail="No validated atomisation was obtained; atomicity is unproven. " + record.response.rationale))
    if len(record.response.children) > service.replan_policy.max_children_per_split:
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.BUDGET_EXHAUSTED,
                      detail="Configured child-count safety budget reached; human escalation required."))
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    try:
        if state.canonical_development_base != record.request.canonical_revision or state.canonical_ref != record.request.canonical_ref:
            raise ValueError("trusted canonical revision changed during replanning")
        digest = validate_split(record, BehaviorSplitValidationContext(contract, state.behavior_replans[:-1], service.replan_policy))
        replacement = _replace_parent(contract, record)
    except ValueError as error:
        detail = str(error)
        if _repairable_split_validation_error(detail) and not record.correction_attempted:
            return await _correct_invalid_split(service, context, state, project, record, detail)
        exhausted_response = record.response.raw_response if record.response else None
        if record.correction_attempted:
            record = replace(
                record,
                validation_errors=(*record.validation_errors, detail),
                rejected_responses=(
                    *record.rejected_responses,
                    *(tuple([exhausted_response]) if exhausted_response is not None else ()),
                ),
            )
            detail = f"proposal correction exhausted: {detail}"
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.INVALID_SPLIT, detail=detail,
                                               rejected_response=exhausted_response))
    superseded = replace(record, phase=BehaviorReplanPhase.SUPERSEDED, structure_digest=digest)

    canonical_revision = state.canonical_development_base
    if canonical_revision is None:
        raise ValueError("behavior replan requires a trusted canonical revision")
    if project.trusted_base_sha != canonical_revision:
        TrustedProjectRevisionSynchronizer(service.environment).synchronize(
            project.project_id,
            canonical_revision,
        )

    updated = replace(_with_record(state, superseded), contract_payload=replacement.to_dict(), current_scenario_id=None)
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.BEHAVIOR_SPLIT, updated, project, behavior_ref=record.request.parent.ref)


async def _correct_invalid_split(
    service: StrictTddFeatureApplicationService,
    context: FeatureReplanContext,
    state: StrictTddFeatureState,
    project: DevelopmentProject,
    record: BehaviorReplanRecord,
    validation_error: str,
    format_only: bool = False,
):
    from core.development.strict_tdd_feature_application_advance import _result_for

    rejected = record.response.raw_response if record.response is not None else (record.rejected_response or "")
    started = replace(
        record,
        phase=BehaviorReplanPhase.CORRECTION_STARTED,
        correction_attempted=True,
        validation_errors=(*record.validation_errors, validation_error),
        rejected_response=rejected,
        rejected_responses=(*record.rejected_responses, rejected),
    )
    service.states.save(_with_record(state, started))
    try:
        response = await service.contract_planner.correct_replan_requirement(
            BehaviorReplanCorrectionRequest(record.request, rejected, validation_error, format_only)
        )
    except RackAiResourceWait:
        service.states.save(state)
        raise
    except BehaviorReplanFailure as error:
        return _block(service, context, replace(
            started,
            blocker=error.kind,
            detail=f"proposal correction failed: {error.detail}",
            rejected_response=error.raw_response,
            rejected_responses=(
                *started.rejected_responses,
                *(tuple([error.raw_response]) if error.raw_response is not None else ()),
            ),
        ))
    received = replace(started, phase=BehaviorReplanPhase.RECEIVED, response=response, blocker=None, detail=None)
    updated = _with_record(state, received)
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED, updated, project,
                       behavior_ref=record.request.parent.ref, reasoning=True)


def _repairable_split_validation_error(detail: str) -> bool:
    integrity_prefixes = (
        "trusted canonical revision changed",
        "parent changed since replan request",
        "completed behavior changed since replan request",
    )
    return not detail.startswith(integrity_prefixes)


def _replace_parent(contract: BehaviorContract, record: BehaviorReplanRecord) -> BehaviorContract:
    if record.response is None:
        raise ValueError("parent replacement requires children")
    parent_ref = record.request.parent.ref
    requirements: list[BehaviorContractRequirement] = []
    for behavior in contract.observable_requirements:
        if behavior.ref == parent_ref:
            requirements.extend(record.response.children)
        elif parent_ref in behavior.depends_on:
            dependencies = [ref for dep in behavior.depends_on for ref in (record.child_refs if dep == parent_ref else (dep,))]
            requirements.append(replace(behavior, depends_on=dependencies))
        else:
            requirements.append(behavior)
    return replace(contract, observable_requirements=requirements)


def _with_record(state: StrictTddFeatureState, record: BehaviorReplanRecord) -> StrictTddFeatureState:
    return replace(state, behavior_replans=(*state.behavior_replans[:-1], record))


def _block(service: StrictTddFeatureApplicationService, context: FeatureReplanContext, record: BehaviorReplanRecord):
    from core.development.strict_tdd_feature_application_advance import _result_for

    state, project = context.state, context.project
    if record.blocker is None:
        raise ValueError("replan blocker requires a typed reason")
    phase = BehaviorReplanPhase.FAILED
    updated = replace(_with_record(state, replace(record, phase=phase)), status=StrictTddFeatureStatus.BLOCKED.value,
                      blocked_reason=record.blocker.value)
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.BLOCKED, updated, project, updated.blocked_reason,
                       record.request.parent.ref, reasoning=record.phase in {
                           BehaviorReplanPhase.STARTED,
                           BehaviorReplanPhase.CORRECTION_STARTED,
                       } and record.blocker != BehaviorReplanBlocker.INTERRUPTED)
