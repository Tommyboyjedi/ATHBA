"""Structural progress checks; semantic coverage remains a Planner/review responsibility."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re

from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.behavior_replan_domain import (
    BehaviorReplanDisposition, BehaviorReplanPolicy, BehaviorReplanRecord,
)
from core.development.behavior_replanning import child_ref
from core.development.scenario_drafting_domain import (
    MAX_TESTER_SCENARIO_ATTEMPTS, ScenarioDraftRunState, ScenarioDraftStatus,
)


SEMANTIC_REJECTIONS = frozenset({"semantic_repair_required", "wrong_behavior", "insufficient_evidence", "candidate_invalid", "candidate_unchanged"})
INFRASTRUCTURE_ATTEMPT_STATUSES = frozenset({
    "intent_review_protocol_failure", "scenario_harness_failure", "intent_protocol_failure",
})


def replan_worthy(draft: ScenarioDraftRunState) -> bool:
    if (draft.status != ScenarioDraftStatus.ATTEMPTS_EXHAUSTED.value
            or draft.approved_microcycle is not None or draft.harness_failure_evidence is not None
            or tuple(item.attempt_number for item in draft.attempts) != tuple(range(1, MAX_TESTER_SCENARIO_ATTEMPTS + 1))):
        return False
    if any(item.intent_protocol_failure is not None or item.status in INFRASTRUCTURE_ATTEMPT_STATUSES for item in draft.attempts):
        return False
    return any(
        item.status in SEMANTIC_REJECTIONS and item.feedback
        and (item.candidate_revision is not None or item.candidate_assessment is not None)
        for item in draft.attempts
    )


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def structure_digest(children: tuple[BehaviorContractRequirement, ...]) -> str:
    shapes = sorted((" ".join(sorted(normalized(item.observable_outcome).split())), tuple(sorted(item.source_refs)),
                     normalized(item.error_expectation or ""), item.preserves_state_on_failure) for item in children)
    return sha256(json.dumps(shapes, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class BehaviorSplitValidationContext:
    contract: BehaviorContract
    history: tuple[BehaviorReplanRecord, ...]
    policy: BehaviorReplanPolicy


def validate_split(record: BehaviorReplanRecord, context: BehaviorSplitValidationContext) -> str:
    contract, history, policy = context.contract, context.history, context.policy
    response = record.response
    if response is None or response.disposition != BehaviorReplanDisposition.SPLIT:
        raise ValueError("split validation requires a split response")
    parent = record.request.parent
    children = response.children
    if not 2 <= len(children) <= policy.max_children_per_split:
        raise ValueError("split child count outside configured safety budget")
    active = {item.ref: item for item in contract.observable_requirements}
    if active.get(parent.ref) != parent:
        raise ValueError("parent changed since replan request")
    if any(active.get(item.ref) != item for item in record.request.completed_requirements):
        raise ValueError("completed behavior changed since replan request")
    forbidden = {normalized(item.observable_outcome) for item in active.values()}
    forbidden.update(normalized(item.request.parent.observable_outcome) for item in history)
    outcomes = [normalized(item.observable_outcome) for item in children]
    structural_outcomes = {tuple(sorted(item.split())) for item in outcomes}
    if len(structural_outcomes) != len(children) or any(not item or item in forbidden for item in outcomes):
        raise ValueError("non-progressing split: unchanged parent, ancestor, existing behavior or duplicate children")
    if any(set(normalized(parent.observable_outcome).split()).issubset(set(item.split())) for item in outcomes):
        raise ValueError("child reproduces the entire parent outcome")
    refs = set(parent.source_refs)
    covered: set[str] = set()
    reserved = set(active) | {item.request.parent.ref for item in history}
    for index, child in enumerate(children, 1):
        if child.ref != child_ref(parent.ref, index) or child.ref in reserved:
            raise ValueError("child identity is not a unique deterministic descendant")
        if not set(child.source_refs).issubset(refs) or len(set(child.source_refs)) != len(child.source_refs):
            raise ValueError("child source refs must be unique and drawn from parent")
        if child.depends_on != parent.depends_on:
            raise ValueError("child dependencies must inherit parent dependencies")
        if parent.preserves_state_on_failure and not child.preserves_state_on_failure:
            raise ValueError("split drops state-preservation obligation")
        covered.update(child.source_refs)
    if covered != refs:
        raise ValueError("split drops parent source coverage")
    if parent.error_expectation and not any(child.error_expectation == parent.error_expectation for child in children):
        raise ValueError("split must retain the parent error expectation in at least one child")
    digest = structure_digest(children)
    if digest in {item.structure_digest for item in history if item is not record}:
        raise ValueError("repeated identical split structure")
    return digest
