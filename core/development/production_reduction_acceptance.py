"""Reuse independent frontier GREEN and accumulated regression for every trial."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION, REGRESSION_INFRASTRUCTURE_FAILURE,
    DeterministicRegressionRequest, DeterministicRegressionResult,
    DeterministicRegressionService,
)
from core.development.microcycle_domain import (
    BoundaryAssessment, BoundaryClassificationRequest, BoundaryOutcome,
    FrontierExecutionRequest, LanguageTestAdapter, RegressionCommandReport,
)
from core.development.production_reduction_domain import ProductionReductionRequest


@dataclass(frozen=True)
class ReductionFrontierCheckRequest:
    authority: ProductionReductionRequest
    workspace: Path
    deadline: float


class FrontierReductionVerifier:
    """Use the configured language boundary without rematerialising immutable tests."""

    def __init__(self, adapter: LanguageTestAdapter):
        self.adapter = adapter

    def verify(self, request: ReductionFrontierCheckRequest) -> BoundaryAssessment:
        source = request.authority.frontier_authority
        if source.artifact.adapter_id != self.adapter.descriptor.adapter_id:
            raise ValueError("reduction frontier has no configured language capability")
        diagnostic = self.adapter.execute_frontier(FrontierExecutionRequest(
            source.artifact, str(request.workspace), source.test_path,
            source.production_path, deadline=request.deadline, materialise_test=False,
        ))
        return self.adapter.classify_boundary(BoundaryClassificationRequest(
            diagnostic, source.artifact, source.active_fragment, source.prior_frontier_status,
        ))


def verify_reduction_acceptance(
    request: ReductionFrontierCheckRequest,
    capabilities: tuple[FrontierReductionVerifier, DeterministicRegressionService],
) -> tuple[BoundaryAssessment, DeterministicRegressionResult]:
    verifier, regression = capabilities
    frontier = verifier.verify(request)
    source = request.authority
    if frontier.outcome != BoundaryOutcome.GREEN.value:
        infrastructure = frontier.outcome == BoundaryOutcome.INFRASTRUCTURE_FAILURE.value
        report = RegressionCommandReport(
            source.current_frontier_test, (), None,
            "infrastructure_failure" if infrastructure else "failed",
            frontier.diagnostic.message,
        )
        return frontier, DeterministicRegressionResult(
            REGRESSION_INFRASTRUCTURE_FAILURE if infrastructure else ACCUMULATED_REGRESSION,
            (report,), (),
        )
    result = regression.run(DeterministicRegressionRequest(
        request.workspace, source.regression_command, source.current_frontier_test,
        source.prior_completed_test_nodes, source.include_accepted_suite,
        deadline=request.deadline,
    ))
    return frontier, result
