"""Compatibility loop over the one-transition strict microcycle API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.development.strict_microcycle import StrictMicrocycleOutcome, StrictMicrocycleRequest
from core.development.strict_tdd_transitions import MicrocycleTransitionKind

MAX_COMPATIBILITY_TRANSITIONS = 100

if TYPE_CHECKING:
    from core.development.strict_microcycle import StrictMicrocycleService


@dataclass(frozen=True)
class CompatibilityLoopState:
    transitions: int = 0
    developer_submissions: int = 0


class StrictMicrocycleRunLoop:
    """Preserves the old run API by repeatedly invoking one persisted advance."""

    def __init__(self, service: StrictMicrocycleService):
        self.service = service

    async def run(self, request: StrictMicrocycleRequest) -> StrictMicrocycleOutcome:
        progress = CompatibilityLoopState()
        state = request.initial_state
        for _ in range(MAX_COMPATIBILITY_TRANSITIONS):
            advanced = await self.service.advance(request)
            state = advanced.state
            progress = CompatibilityLoopState(
                progress.transitions + 1,
                progress.developer_submissions + int(advanced.rack_ai_invoked),
            )
            terminal = self._terminal_status(advanced.kind, advanced.blocker_or_replan_reason)
            if terminal is not None:
                return StrictMicrocycleOutcome(state, terminal, progress.developer_submissions)
            if advanced.kind == MicrocycleTransitionKind.ACCUMULATED_REGRESSION:
                return StrictMicrocycleOutcome(state, "accumulated_regression", progress.developer_submissions)
            if advanced.kind == MicrocycleTransitionKind.REGRESSION_INFRASTRUCTURE_FAILURE:
                return StrictMicrocycleOutcome(state, "regression_infrastructure_failure", progress.developer_submissions)
            if advanced.kind == MicrocycleTransitionKind.SCENARIO_COMPLETED:
                if self.service.behavior_completion is None:
                    return StrictMicrocycleOutcome(state, "scenario_complete", progress.developer_submissions)
        return StrictMicrocycleOutcome(state, "transition_safety_guard_exhausted", progress.developer_submissions)

    @staticmethod
    def _terminal_status(kind: MicrocycleTransitionKind, reason: str | None) -> str | None:
        if kind == MicrocycleTransitionKind.BEHAVIOR_COMPLETED:
            return "behavior_complete"
        if kind == MicrocycleTransitionKind.BEHAVIOR_REPLAN_REQUIRED:
            return "replan_required"
        if kind == MicrocycleTransitionKind.DEVELOPER_CANDIDATE_REJECTED:
            return "developer_candidate_rejected"
        if kind == MicrocycleTransitionKind.BLOCKED:
            return reason or "blocked"
        if kind == MicrocycleTransitionKind.ATTEMPTS_EXHAUSTED:
            return reason or "attempts_exhausted"
        return None
