"""Loop extracted from StrictMicrocycleService to keep its orchestration surface bounded."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from core.development.deterministic_regression import ACCUMULATED_REGRESSION, REGRESSION_CLEAR
from core.development.microcycle_domain import ScenarioCompletion
from core.development.strict_microcycle import (
    CompletedBehaviorRouteRequest,
    DeveloperExecutionContext,
    FrontierExecutionContext,
    RegressionRepairContext,
    StrictMicrocycleOutcome,
    StrictMicrocycleRequest,
    _advance,
    _complete_revision_lifecycle,
    _load_state,
    _route_completed_behavior,
)

if TYPE_CHECKING:
    from core.development.strict_microcycle import StrictMicrocycleService


class StrictMicrocycleRunLoop:
    """Advance one persisted strict scenario until it reaches a durable boundary."""

    def __init__(self, service: StrictMicrocycleService):
        self.service = service

    async def run(self, request: StrictMicrocycleRequest) -> StrictMicrocycleOutcome:
        service = self.service
        state = _load_state(service.state_store, service.adapters, request)
        adapter = service.adapters.for_language(state.model.language_id)
        submitted = 0
        while True:
            if state.completion.status == "behavior_complete":
                _complete_revision_lifecycle(request, state)
                return StrictMicrocycleOutcome(state, "behavior_complete", submitted)
            if state.completion.status == "scenario_complete":
                routed = await _route_completed_behavior(
                    CompletedBehaviorRouteRequest(
                        request, state, adapter, service.behavior_completion, service.behavior_repair,
                        service.repair_service, service.state_store,
                    )
                )
                state, outcome = routed.state, routed.outcome
                submitted += outcome.developer_submissions
                if outcome.status == "continue":
                    continue
                if outcome.status == "behavior_complete":
                    _complete_revision_lifecycle(request, state)
                return StrictMicrocycleOutcome(state, outcome.status, submitted)
            if state.regression.status == REGRESSION_CLEAR:
                if state.frontier.index == len(state.fragments) - 1:
                    state = replace(
                        state, completion=ScenarioCompletion("scenario_complete", state.development_base_revision)
                    )
                    service.state_store.save(state)
                    continue
                state = _advance(state, state.development_base_revision)
                service.state_store.save(state)
                continue
            if state.regression.status == ACCUMULATED_REGRESSION:
                state, repair = await service.repair_service.repair(
                    RegressionRepairContext(request, state, adapter)
                )
                submitted += repair.developer_submissions
                if repair.status != "green":
                    return StrictMicrocycleOutcome(state, repair.status, submitted)
                continue
            if state.current_accepted_red_revision is not None:
                state, result = await service._developer(DeveloperExecutionContext(request, state))
                submitted += result.developer_submissions
                if result.status != "advanced":
                    return StrictMicrocycleOutcome(state, result.status, submitted)
                continue
            outcome = service._execute_frontier(FrontierExecutionContext(request, state, adapter))
            state = outcome.state
            if state.current_accepted_red_revision is not None:
                continue
            if outcome.status != "green":
                return StrictMicrocycleOutcome(state, outcome.status, submitted)
