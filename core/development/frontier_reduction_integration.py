"""Apply deterministic reduction only to an ordinary regression-clear frontier."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Protocol

from core.development.deterministic_regression import REGRESSION_CLEAR
from core.development.microcycle_domain import MicrocycleState
from core.development.production_reduction import ProductionReductionRequest, ProductionReductionResult

if TYPE_CHECKING:
    from core.development.strict_microcycle import StrictMicrocycleRequest


class FrontierProductionReducer(Protocol):
    def reduce(self, request: ProductionReductionRequest) -> ProductionReductionResult: ...


@dataclass(frozen=True)
class FrontierReductionContext:
    request: StrictMicrocycleRequest
    state: MicrocycleState
    adapter_id: str


@dataclass(frozen=True)
class FrontierReductionPromotion:
    state: MicrocycleState
    evidence_ref: str | None = None


def reduce_frontier_candidate(
    reducer: FrontierProductionReducer | None,
    context: FrontierReductionContext,
) -> FrontierReductionPromotion:
    state = context.state
    if reducer is None:
        return FrontierReductionPromotion(state)
    if state.regression.status != REGRESSION_CLEAR:
        raise ValueError("production reduction requires a regression-clear frontier")
    candidate = state.candidate_chain_revision
    attempts = tuple(item for item in state.developer_attempts
                     if item.frontier_index == state.frontier.index)
    matching = tuple(item for item in attempts if item.candidate_revision == candidate)
    if candidate is None or not matching:
        return FrontierReductionPromotion(state)
    current = matching[-1]
    request = context.request
    reduction = reducer.reduce(ProductionReductionRequest(
        repository_root=request.repository_root,
        scenario_id=state.scenario_draft.scenario_id,
        frontier_index=state.frontier.index,
        baseline_revision=state.development_base_revision,
        accepted_red_revision=attempts[0].base_revision,
        developer_input_revision=current.base_revision,
        candidate_revision=candidate,
        production_paths=(request.production_path,),
        current_frontier_test=state.model.canonical_test_identity,
        regression_command=state.regression.command,
        prior_completed_test_nodes=request.prior_completed_test_nodes,
        include_accepted_suite=request.include_accepted_regression_suite,
        adapter_id=context.adapter_id,
        initial_regression=state.regression,
        required_artifacts=(request.production_path,),
    ))
    if not reduction.revision or reduction.regression.status != REGRESSION_CLEAR:
        raise ValueError("production reduction returned no verified GREEN candidate")
    updated = replace(state, candidate_chain_revision=reduction.revision,
                      regression=reduction.regression)
    return FrontierReductionPromotion(updated, reduction.evidence_ref)
