from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import Enum

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.contract_run_domain import BehaviorContractRunState, TddStepProposal
from core.development.failure_records import FailureObservation, SplitChildStep, WorkPacketSplit
from core.development.failure_state import FailureProgressState, active_failure_progress_state
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest

MAX_SPLIT_CHILDREN = 2
MAX_SPLIT_DEPTH = 2


class SplitDecisionStatus(str, Enum):
    SPLIT = "split"
    CANNOT_SPLIT = "cannot_split"


@dataclass(frozen=True)
class ResourceSplitPlannerRequest:
    contract: BehaviorContract
    requirement: BehaviorContractRequirement
    step: TddStepProposal
    evidence: FailureObservation
    trusted_revision: str | None
    split_depth: int
    repository_material: dict[str, object] | None = None


@dataclass(frozen=True)
class ResourceSplitDecision:
    status: SplitDecisionStatus
    rationale: str
    child_steps: list[SplitChildStep] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("resource split rationale must be non-empty")
        if self.status is SplitDecisionStatus.CANNOT_SPLIT and self.child_steps:
            raise ValueError("cannot_split decisions must not include child steps")
        if self.status is SplitDecisionStatus.SPLIT:
            if len(self.child_steps) < 2 or len(self.child_steps) > MAX_SPLIT_CHILDREN:
                raise ValueError("split decisions must include exactly two child steps")
            child_ids = [child.step_id for child in self.child_steps]
            if len(set(child_ids)) != len(child_ids):
                raise ValueError("split child step ids must be unique")
            keys = [child.equivalence_key() for child in self.child_steps]
            if len(set(keys)) != len(keys):
                raise ValueError("equivalent duplicate split children are not allowed")


@dataclass(frozen=True)
class SplitApprovalResolution:
    failure_progress: FailureProgressState
    completed_requirement_refs: list[str]
    current_pool: str
    blocked_reason: str | None


class ResourceLimitSplitPlanner:
    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def decide(self, request: ResourceSplitPlannerRequest | None = None, **legacy) -> ResourceSplitDecision:
        request = request or ResourceSplitPlannerRequest(
            legacy["contract"],
            legacy["requirement"],
            legacy["step"],
            legacy["evidence"],
            legacy.get("trusted_revision"),
            legacy["split_depth"],
            legacy.get("repository_material"),
        )
        reasoning_request = ReasoningRequest(
            purpose="athba_resource_limit_split",
            project_id=request.contract.project_id,
            requires_large_context=False,
            prompt=json.dumps({
                "instruction": "Return exactly one bounded JSON decision. Split only when the failed semantic step can be decomposed into at most two smaller semantic child steps that preserve the same requirement, test path, production path, and allowed-path boundary. Child steps must remain observable, independently executable, and must not broaden scope or invent new requirements.",
                "schema": {
                    "status": "split|cannot_split",
                    "rationale": "string",
                    "child_steps": [{
                        "step_id": "string",
                        "requirement_refs": ["string"],
                        "focused_behavior": "string",
                        "test_name": "string",
                        "expected_result": "string",
                        "test_path": "string",
                        "production_path": "string",
                        "red_objective": "string",
                        "green_objective": "string",
                        "reason_next_smallest": "string",
                        "depends_on": ["string"],
                    }],
                },
                "max_child_steps": MAX_SPLIT_CHILDREN,
                "max_split_depth": MAX_SPLIT_DEPTH,
                "current_split_depth": request.split_depth,
                "trusted_revision": request.trusted_revision,
                "failed_requirement": request.requirement.to_dict(),
                "failed_step": request.step.to_dict(),
                "resource_limit_evidence": request.evidence.to_dict(),
                "repository_material": request.repository_material,
            }, sort_keys=True),
        )
        result = await self.gateway.reason(reasoning_request)
        decision = _resource_split_decision(result.text)
        return _validated_split_decision(request, decision)


def split_record(request: ResourceSplitPlannerRequest, decision: ResourceSplitDecision, parent_work_unit_id: str) -> WorkPacketSplit:
    return WorkPacketSplit(
        parent_work_unit_id=parent_work_unit_id,
        parent_step_id=request.step.step_id,
        parent_requirement_ref=request.requirement.ref,
        child_work_unit_ids=[child.step_id for child in decision.child_steps],
        preserved_objective=request.step.green_objective if request.step.green_objective else request.step.red_objective,
        rationale=decision.rationale,
        trusted_revision=request.trusted_revision,
        split_depth=request.split_depth,
        child_steps=list(decision.child_steps),
    )


def next_ready_split_child(run_state: BehaviorContractRunState) -> SplitChildStep | None:
    for split in reversed(run_state.failure_progress.splits):
        if not split.child_steps or _is_completed_split(split):
            continue
        completed = set(split.completed_child_ids)
        ready_children = [child for child in split.child_steps if child.step_id not in completed and set(child.depends_on).issubset(completed)]
        if ready_children:
            return ready_children[0]
        raise ValueError(f"split {split.parent_step_id or split.parent_work_unit_id} has no ready child")
    return None


def trusted_revision_for_child(progress: FailureProgressState, step_id: str) -> str | None:
    parent = _parent_split(progress, step_id)
    if parent is None or parent.completed_child_ids:
        return None
    return parent.trusted_revision


def step_proposal(child: SplitChildStep) -> TddStepProposal:
    return TddStepProposal(
        step_id=child.step_id,
        requirement_refs=list(child.requirement_refs),
        focused_behavior=child.focused_behavior,
        test_name=child.test_name,
        expected_result=child.expected_result,
        test_path=child.test_path,
        production_path=child.production_path,
        red_objective=child.red_objective,
        green_objective=child.green_objective,
        reason_next_smallest=child.reason_next_smallest,
    )


def split_depth_for_step(progress: FailureProgressState, step_id: str) -> int:
    parent = _parent_split(progress, step_id)
    if parent is None:
        return 1
    return parent.split_depth + 1


def has_pending_split_children(progress: FailureProgressState) -> bool:
    return any(not _is_completed_split(split) for split in progress.splits if split.child_steps)


def record_completed_split_child(progress: FailureProgressState, step_id: str) -> FailureProgressState:
    updated = progress
    changed = True
    while changed:
        updated, changed = _record_completion_once(updated, step_id)
        if changed:
            step_id = _completed_parent_step(updated, step_id) or step_id
    return updated


def split_aware_success_state(progress: FailureProgressState) -> FailureProgressState:
    if has_pending_split_children(progress):
        return replace(progress, blocker=None)
    return active_failure_progress_state(progress)


def approval_resolution(run_state: BehaviorContractRunState, step: TddStepProposal) -> SplitApprovalResolution | None:
    progress = record_completed_split_child(run_state.failure_progress, step.step_id)
    if progress == run_state.failure_progress:
        return None
    if has_pending_split_children(progress):
        return SplitApprovalResolution(
            failure_progress=split_aware_success_state(progress),
            completed_requirement_refs=list(run_state.completed_requirement_refs),
            current_pool="tdd_ready",
            blocked_reason="split child approved; split work remains",
        )
    completed_refs = sorted(set(run_state.completed_requirement_refs).union(step.requirement_refs))
    return SplitApprovalResolution(
        failure_progress=split_aware_success_state(progress),
        completed_requirement_refs=completed_refs,
        current_pool="approved",
        blocked_reason=None,
    )


def _record_completion_once(progress: FailureProgressState, step_id: str) -> tuple[FailureProgressState, bool]:
    splits: list[WorkPacketSplit] = []
    changed = False
    completed_parent: str | None = None
    for split in progress.splits:
        if step_id in split.child_step_ids and step_id not in split.completed_child_ids:
            completed_ids = [*split.completed_child_ids, step_id]
            split = replace(split, completed_child_ids=completed_ids)
            changed = True
            if set(completed_ids) == set(split.child_step_ids):
                completed_parent = split.parent_step_id
        splits.append(split)
    if not changed:
        return progress, False
    updated = replace(progress, splits=splits)
    if completed_parent is None:
        return updated, True
    parent_updated, _ = _record_completion_once(updated, completed_parent)
    return parent_updated, True


def _completed_parent_step(progress: FailureProgressState, step_id: str) -> str | None:
    for split in progress.splits:
        if split.parent_step_id and step_id in split.child_step_ids and set(split.completed_child_ids) == set(split.child_step_ids):
            return split.parent_step_id
    return None


def _is_completed_split(split: WorkPacketSplit) -> bool:
    return bool(split.child_steps) and set(split.completed_child_ids) == set(split.child_step_ids)


def _parent_split(progress: FailureProgressState, step_id: str) -> WorkPacketSplit | None:
    for split in progress.splits:
        if step_id in split.child_step_ids:
            return split
    return None


def _resource_split_decision(payload_text: str) -> ResourceSplitDecision:
    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("resource split decision must be a JSON object")
    return ResourceSplitDecision(
        status=SplitDecisionStatus(str(payload["status"])),
        rationale=str(payload["rationale"]),
        child_steps=[SplitChildStep.from_dict(dict(item)) for item in payload.get("child_steps", [])],
    )


def _validated_split_decision(request: ResourceSplitPlannerRequest, decision: ResourceSplitDecision) -> ResourceSplitDecision:
    if request.split_depth > MAX_SPLIT_DEPTH:
        raise ValueError("split depth exceeds configured maximum")
    if decision.status is SplitDecisionStatus.CANNOT_SPLIT:
        return decision
    requirement_ref = request.requirement.ref
    child_ids = {child.step_id for child in decision.child_steps}
    for child in decision.child_steps:
        if child.step_id == request.step.step_id:
            raise ValueError("split child step id must differ from the parent step id")
        if child.requirement_refs != [requirement_ref]:
            raise ValueError("split child steps must retain the parent requirement ref")
        if child.test_path != request.step.test_path:
            raise ValueError("split child steps must preserve the parent test path")
        if child.production_path != request.step.production_path:
            raise ValueError("split child steps must preserve the parent production path")
        if not set(child.depends_on).issubset(child_ids - {child.step_id}):
            raise ValueError("split child dependencies must reference sibling child ids")
    return decision
