"""Persisted feature transitions for exhausted-parent recovery."""
from __future__ import annotations

from dataclasses import dataclass, replace

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.behavior_replan_domain import (
    BehaviorReplanBlocker, BehaviorReplanDisposition, BehaviorReplanPhase,
    BehaviorReplanRecord, BehaviorReplanRequest,
)
from core.development.behavior_replan_validation import BehaviorSplitValidationContext, replan_worthy, validate_split
from core.development.behavior_replanning import BehaviorReplanFailure
from core.development.project_environment import DevelopmentProject
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.scenario_drafting_domain import ScenarioDraftRunState
from core.development.strict_tdd_feature_application import StrictTddFeatureApplicationService
from core.development.strict_tdd_feature_domain import StrictTddFeatureState, StrictTddFeatureStatus
from core.development.strict_tdd_transitions import FeatureTransitionKind


@dataclass(frozen=True)
class FeatureReplanContext:
    state: StrictTddFeatureState
    project: DevelopmentProject


def require_replan(
    state: StrictTddFeatureState,
    draft: ScenarioDraftRunState,
    developer_exhaustion: bool = False,
    failure_evidence: tuple[str, ...] = (),
) -> StrictTddFeatureState | None:
    if not developer_exhaustion and not replan_worthy(draft):
        return None
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    parent = next(item for item in contract.observable_requirements if item.ref == draft.behavior_ref)
    if (draft.scenario_id != state.current_scenario_id
            or draft.development_base_revision != state.canonical_development_base
            or tuple(parent.source_refs) != draft.source_requirement_refs):
        raise ValueError("exhausted draft differs from trusted feature identity")
    if any(item.request.parent.ref == parent.ref for item in state.behavior_replans):
        raise ValueError("parent already has durable replan evidence")
    completed = {item.behavior_ref for item in state.completed_behaviors}
    lineage = next(((*item.request.lineage, item.request.parent.ref)
                    for item in state.behavior_replans if parent.ref in item.child_refs), ())
    request = BehaviorReplanRequest(
        state.project_id, contract.requirement_source, parent,
        tuple(item for item in contract.source_clauses if item.ref in parent.source_refs),
        draft, tuple(item for item in contract.observable_requirements if item.ref in completed),
        str(state.canonical_ref), str(state.canonical_development_base), lineage,
        failure_evidence=failure_evidence,
    )
    return replace(state, behavior_replans=(*state.behavior_replans, BehaviorReplanRecord(request)),
                   evidence_refs=(*state.evidence_refs, f"feature:{state.project_id}:behavior-replan:{parent.ref}"))


def replan_pending(state: StrictTddFeatureState) -> bool:
    return bool(state.behavior_replans and state.behavior_replans[-1].phase in {
        BehaviorReplanPhase.REQUIRED, BehaviorReplanPhase.STARTED, BehaviorReplanPhase.RECEIVED,
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
    if phase == BehaviorReplanPhase.REQUIRED:
        if len(state.behavior_replans) > service.replan_policy.max_splits:
            return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.UNSPLITTABLE,
                          detail="Configured total split safety budget reached; human escalation required."))
        started = replace(record, phase=BehaviorReplanPhase.STARTED)
        service.states.save(_with_record(state, started))
        try:
            response = await service.contract_planner.replan_requirement(record.request)
        except BehaviorReplanFailure as error:
            return _block(service, context, replace(started, blocker=error.kind, detail=error.detail,
                                                   rejected_response=error.raw_response))
        received = replace(started, phase=BehaviorReplanPhase.RECEIVED, response=response)
        updated = _with_record(state, received)
        service.states.save(updated)
        return _result_for(FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED, updated, project,
                           behavior_ref=record.request.parent.ref, reasoning=True)
    if record.response is None:
        raise ValueError("received replan has no response")
    if record.response.disposition == BehaviorReplanDisposition.UNSPLITTABLE:
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.UNSPLITTABLE,
                                               detail=record.response.rationale))
    if len(record.response.children) > service.replan_policy.max_children_per_split:
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.UNSPLITTABLE,
                      detail="Configured child-count safety budget reached; human escalation required."))
    contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
    try:
        if state.canonical_development_base != record.request.canonical_revision or state.canonical_ref != record.request.canonical_ref:
            raise ValueError("trusted canonical revision changed during replanning")
        digest = validate_split(record, BehaviorSplitValidationContext(contract, state.behavior_replans[:-1], service.replan_policy))
        replacement = _replace_parent(contract, record)
    except ValueError as error:
        return _block(service, context, replace(record, blocker=BehaviorReplanBlocker.INVALID_SPLIT, detail=str(error)))
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


def _replace_parent(contract: BehaviorContract, record: BehaviorReplanRecord) -> BehaviorContract:
    if record.response is None:
        raise ValueError("parent replacement requires children")
    parent_ref = record.request.parent.ref
    completed = {item.ref for item in record.request.completed_requirements}
    requirements: list[BehaviorContractRequirement] = []
    for behavior in contract.observable_requirements:
        if behavior.ref == parent_ref:
            requirements.extend(record.response.children)
        elif parent_ref in behavior.depends_on:
            if behavior.ref in completed:
                raise ValueError("completed behavior cannot depend on the unresolved parent")
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
    phase = BehaviorReplanPhase.UNSPLITTABLE if record.blocker == BehaviorReplanBlocker.UNSPLITTABLE else BehaviorReplanPhase.FAILED
    updated = replace(_with_record(state, replace(record, phase=phase)), status=StrictTddFeatureStatus.BLOCKED.value,
                      blocked_reason=record.blocker.value)
    service.states.save(updated)
    return _result_for(FeatureTransitionKind.BLOCKED, updated, project, updated.blocked_reason,
                       record.request.parent.ref, reasoning=record.phase == BehaviorReplanPhase.STARTED and record.blocker != BehaviorReplanBlocker.INTERRUPTED)
