"""Reuse independent frontier GREEN and accumulated regression for every trial."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from pathlib import Path

from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION, REGRESSION_INFRASTRUCTURE_FAILURE,
    DeterministicRegressionRequest, DeterministicRegressionResult,
    DeterministicRegressionService,
)
from core.development.microcycle_domain import (
    BoundaryAssessment, BoundaryClassificationRequest, BoundaryOutcome,
    FrontierExecutionRequest, LanguageTestAdapter, RegressionCommandReport, BoundaryDiagnostic,
)
from core.development.production_reduction_domain import (
    ConsolidatedReductionRequest, ProductionReductionRequest, ReductionRequest,
)


@dataclass(frozen=True)
class ReductionFrontierCheckRequest:
    authority: ReductionRequest
    workspace: Path
    deadline: float


class FrontierReductionVerifier:
    """Use the configured language boundary without rematerialising immutable tests."""

    def __init__(self, adapter: LanguageTestAdapter):
        self.adapter = adapter

    def verify(self, request: ReductionFrontierCheckRequest) -> BoundaryAssessment:
        if not isinstance(request.authority, ProductionReductionRequest):
            raise ValueError("frontier verifier requires real frontier authority")
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


@dataclass(frozen=True)
class CompletionReductionAssessment:
    assessments: tuple[BoundaryAssessment, ...]

    @property
    def outcome(self) -> str:
        return self.selected.outcome

    @property
    def diagnostic(self) -> BoundaryDiagnostic:
        return self.selected.diagnostic

    @property
    def selected(self) -> BoundaryAssessment:
        return next((item for item in self.assessments
                     if item.outcome != BoundaryOutcome.GREEN.value), self.assessments[-1])


class CompletionReductionVerifier:
    """Execute every actual approved completed test; no RED is manufactured."""

    def __init__(self, adapter: LanguageTestAdapter):
        self.adapter = adapter

    def verify(self, request: ReductionFrontierCheckRequest) -> CompletionReductionAssessment:
        source = request.authority
        if not isinstance(source, ConsolidatedReductionRequest) or not source.test_authorities:
            raise ValueError("completion verifier requires approved completed test authority")
        assessments = []
        for item in source.test_authorities:
            if item.artifact.adapter_id != self.adapter.descriptor.adapter_id:
                raise ValueError("completion test has no configured language capability")
            diagnostic = self.adapter.execute_frontier(FrontierExecutionRequest(
                item.artifact, str(request.workspace), item.test_path,
                item.production_path, deadline=request.deadline, materialise_test=False,
            ))
            assessment = self.adapter.classify_boundary(BoundaryClassificationRequest(
                diagnostic, item.artifact, item.active_fragment, item.prior_frontier_status,
            ))
            assessments.append(assessment)
            if assessment.outcome != BoundaryOutcome.GREEN.value:
                break
        return CompletionReductionAssessment(tuple(assessments))


class ReductionVerifier(Protocol):
    def verify(self, request: ReductionFrontierCheckRequest) -> BoundaryAssessment | CompletionReductionAssessment: ...


def verify_reduction_acceptance(
    request: ReductionFrontierCheckRequest,
    capabilities: tuple[ReductionVerifier, DeterministicRegressionService],
) -> tuple[BoundaryAssessment | CompletionReductionAssessment, DeterministicRegressionResult]:
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
