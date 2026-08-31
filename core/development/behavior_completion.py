"""One behavior-level Senior Review after a strict scenario is fully green."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from core.development.microcycle_domain import BehaviorReviewState, MicrocycleState

APPROVED = "approved"
REPAIR_REQUIRED = "repair_required"
REPLAN_REQUIRED = "replan_required"


@dataclass(frozen=True)
class BehaviorReviewRequest:
    behavior_ticket: str
    approved_scenario: str
    canonical_test_identity: str
    production_diff: str
    microcycle_evidence: tuple[str, ...]
    regression_evidence: tuple[str, ...]


@dataclass(frozen=True)
class BehaviorReviewResult:
    verdict: str
    rationale: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in {APPROVED, REPAIR_REQUIRED, REPLAN_REQUIRED}:
            raise ValueError("unsupported behavior review verdict")
        if not self.rationale.strip() or any(not item.strip() for item in self.evidence_refs):
            raise ValueError("behavior review evidence is invalid")


class SeniorBehaviorReviewer(Protocol):
    async def review(self, request: BehaviorReviewRequest) -> BehaviorReviewResult: ...


@dataclass(frozen=True)
class NextBehaviorRequest:
    completed_behavior_ticket: str
    completed_revision: str


class NextBehaviorScenarioStarter(Protocol):
    async def start(self, request: NextBehaviorRequest) -> str: ...


@dataclass(frozen=True)
class BehaviorCompletionDependencies:
    reviewer: SeniorBehaviorReviewer
    next_scenario_starter: NextBehaviorScenarioStarter


class BehaviorCompletionService:
    """Reviews exactly once, then starts the next scenario only on approval."""

    def __init__(self, dependencies: BehaviorCompletionDependencies):
        self.reviewer = dependencies.reviewer
        self.next_scenario_starter = dependencies.next_scenario_starter

    async def complete(self, state: MicrocycleState, production_diff: str = "") -> MicrocycleState:
        if state.completion.status != "scenario_complete":
            raise ValueError("behavior review requires a complete scenario")
        if state.behavior_review.verdict == APPROVED:
            return state
        if state.behavior_review.attempts >= 4:
            return replace(state, behavior_review=replace(state.behavior_review, verdict="attempts_exhausted"))
        review = await self.reviewer.review(self._request(state, production_diff))
        reviewed = replace(
            state,
            behavior_review=BehaviorReviewState(review.verdict, state.behavior_review.attempts + 1, review.evidence_refs),
        )
        if review.verdict != APPROVED:
            return reviewed
        ticket = await self.next_scenario_starter.start(
            NextBehaviorRequest(state.scenario_draft.behavior_ref, state.development_base_revision)
        )
        return replace(reviewed, behavior_review=replace(reviewed.behavior_review, next_behavior_ticket=ticket), completion=replace(state.completion, status="behavior_complete"))

    @staticmethod
    def _request(state: MicrocycleState, production_diff: str) -> BehaviorReviewRequest:
        evidence = tuple(item.outcome for item in state.boundary_evidence)
        return BehaviorReviewRequest(
            state.scenario_draft.behavior_ref,
            state.model.complete_source,
            state.model.canonical_test_identity,
            production_diff,
            evidence,
            state.regression.evidence_refs,
        )
