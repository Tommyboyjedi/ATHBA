"""One behavior-level Senior Review after a strict scenario is fully green."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Protocol

from core.development.microcycle_domain import (
    BehaviorReplanState,
    BehaviorReviewState,
    BehaviorReviewVerdict,
    MicrocycleState,
)

APPROVED = BehaviorReviewVerdict.APPROVED.value
REPAIR_REQUIRED = BehaviorReviewVerdict.REPAIR_REQUIRED.value
REPLAN_REQUIRED = BehaviorReviewVerdict.REPLAN_REQUIRED.value


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
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in {APPROVED, REPAIR_REQUIRED, REPLAN_REQUIRED}:
            raise ValueError("unsupported behavior review verdict")
        if not self.rationale.strip() or any(not item.strip() for item in self.evidence_refs):
            raise ValueError("behavior review evidence is invalid")
        if any(not item.strip() for item in self.findings):
            raise ValueError("behavior review findings are invalid")
        if self.verdict == REPAIR_REQUIRED and not self.findings:
            raise ValueError("repair_required requires descriptive findings")
        if self.verdict == APPROVED and self.findings:
            raise ValueError("approved cannot include repair findings")


@dataclass(frozen=True)
class BehaviorCompletionCommand:
    state: MicrocycleState
    production_diff: str = ""
    persist: Callable[[MicrocycleState], object] | None = None


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
    next_scenario_starter: NextBehaviorScenarioStarter | None = None


@dataclass(frozen=True)
class BehaviorReviewTransitionRequest:
    state: MicrocycleState
    result: BehaviorReviewResult
    production_diff: str


class BehaviorCompletionService:
    """Persists one review decision before a later transition can consume it."""

    def __init__(self, dependencies: BehaviorCompletionDependencies):
        self.reviewer = dependencies.reviewer
        self.next_scenario_starter = dependencies.next_scenario_starter

    async def complete(self, command: BehaviorCompletionCommand) -> MicrocycleState:
        state = command.state
        if state.completion.status != "scenario_complete":
            raise ValueError("behavior review requires a complete scenario")
        review = state.behavior_review
        if review.verdict == APPROVED:
            return await self._start_next(command, state)
        if review.verdict in {REPAIR_REQUIRED, REPLAN_REQUIRED, BehaviorReviewVerdict.ATTEMPTS_EXHAUSTED.value}:
            return state
        result = await self.reviewer.review(self._request(command))
        reviewed = replace(state, behavior_review=self._state_after_review(BehaviorReviewTransitionRequest(state, result, command.production_diff)))
        self._persist(command, reviewed)
        return reviewed if result.verdict != APPROVED else await self._start_next(command, reviewed)

    @staticmethod
    def _state_after_review(request: BehaviorReviewTransitionRequest) -> BehaviorReviewState:
        state, result = request.state, request.result
        prior = state.behavior_review
        candidate = state.completion.completed_revision or state.development_base_revision
        replan = (
            BehaviorReplanState(candidate, result.rationale, result.findings, result.evidence_refs)
            if result.verdict == REPLAN_REQUIRED else None
        )
        return BehaviorReviewState(
            result.verdict,
            prior.attempts + 1,
            result.evidence_refs,
            prior.next_behavior_ticket,
            result.rationale,
            () if result.verdict == APPROVED else result.findings,
            candidate,
            prior.repair,
            replan,
            request.production_diff,
        )

    async def _start_next(self, command: BehaviorCompletionCommand, state: MicrocycleState) -> MicrocycleState:
        if state.behavior_review.next_behavior_ticket is not None:
            return state
        if self.next_scenario_starter is None:
            completed = replace(state, completion=replace(state.completion, status="behavior_complete"))
            self._persist(command, completed)
            return completed
        ticket = await self.next_scenario_starter.start(
            NextBehaviorRequest(state.scenario_draft.behavior_ref, state.development_base_revision)
        )
        completed = replace(
            state,
            behavior_review=replace(state.behavior_review, next_behavior_ticket=ticket),
            completion=replace(state.completion, status="behavior_complete"),
        )
        self._persist(command, completed)
        return completed

    @staticmethod
    def _persist(command: BehaviorCompletionCommand, state: MicrocycleState) -> None:
        if command.persist is not None:
            command.persist(state)

    @staticmethod
    def _request(command: BehaviorCompletionCommand) -> BehaviorReviewRequest:
        state = command.state
        evidence = tuple(item.outcome for item in state.boundary_evidence)
        return BehaviorReviewRequest(
            state.scenario_draft.behavior_ref,
            state.model.complete_source,
            state.model.canonical_test_identity,
            command.production_diff,
            evidence,
            state.regression.evidence_refs,
        )
