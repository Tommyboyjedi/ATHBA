"""Execute configured project checks and every preserved accepted test."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from core.delivery_management.evidence import (
    AcceptedContribution, AcceptedEvidenceUnion, AcceptedSourceReader, EvidenceTreeRequest,
)
from core.development.consolidation_language import ConsolidationLanguage, ConsolidationTestSource
from core.development.deterministic_regression import (
    FULL_SUITE_TARGET, ProjectRuntimeExecutor, RuntimeCommandRequest,
)
from core.development.microcycle_domain import (
    BoundaryAssessment, BoundaryClassificationRequest, BoundaryOutcome, FrontierExecutionRequest, RegressionCommandReport,
)
from core.development.post_behavior_git import PostBehaviorGit
from core.development.project_environment import ProjectRuntime
from core.development.test_material import TestMaterialAdapter

INTEGRATION_BUILD_TARGET = "application_build"


@dataclass(frozen=True)
class IntegrationValidationDependencies:
    test_material: TestMaterialAdapter
    language: ConsolidationLanguage
    executor: ProjectRuntimeExecutor


@dataclass(frozen=True)
class IntegrationValidationRequest:
    workspace: Path
    revision: str
    runtime: ProjectRuntime
    contributions: tuple[AcceptedContribution, ...]


@dataclass(frozen=True)
class IntegrationValidationResult:
    passed: bool
    evidence_refs: tuple[str, ...]
    commands: tuple[RegressionCommandReport, ...]
    diagnostic: str = ""
    node_execution: tuple[BoundaryAssessment, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class IntegrationValidator:
    dependencies: IntegrationValidationDependencies

    def validate(self, request: IntegrationValidationRequest) -> IntegrationValidationResult:
        deps = self.dependencies
        git = PostBehaviorGit(request.workspace)
        head = git.command(("rev-parse", "HEAD")).strip()
        if head != request.revision or git.command(("status", "--porcelain", "--untracked-files=no")).strip():
            raise ValueError("integration validation requires the clean exact candidate checkout")
        tests = AcceptedEvidenceUnion(deps.test_material).verify(EvidenceTreeRequest(
            request.workspace, request.revision, request.contributions))
        reports = []
        node_execution = []
        if request.runtime.build_command is not None:
            reports.append(deps.executor.execute(RuntimeCommandRequest(
                request.workspace, INTEGRATION_BUILD_TARGET, tuple(request.runtime.build_command))))
        reports.append(deps.executor.execute(RuntimeCommandRequest(
            request.workspace, FULL_SUITE_TARGET, tuple(request.runtime.test_command))))
        reader = AcceptedSourceReader(request.workspace, deps.test_material)
        for item in tests:
            source = reader.source((request.revision, item.test_name))
            authority = deps.language.authority(ConsolidationTestSource(
                item.delivery_id, item.test_name, source, item.production_path, request.revision))
            diagnostic = deps.language.adapter.execute_frontier(FrontierExecutionRequest(
                authority.artifact, str(request.workspace), item.test_path,
                item.production_path, materialise_test=False))
            assessment = deps.language.adapter.classify_boundary(BoundaryClassificationRequest(
                diagnostic, authority.artifact, authority.active_fragment, authority.prior_frontier_status))
            node_execution.append(assessment)
            reports.append(RegressionCommandReport(item.test_name, tuple(deps.test_material.acceptance_command(item.test_name)),
                0 if assessment.outcome == BoundaryOutcome.GREEN.value else None,
                "passed" if assessment.outcome == BoundaryOutcome.GREEN.value else "failed",
                diagnostic.message))
        dirty = git.command(("status", "--porcelain", "--untracked-files=no")).strip()
        passed = bool(reports) and all(item.status == "passed" for item in reports) and not dirty
        refs = tuple("accepted-test:" + item.test_name + ":" + item.source_sha256 for item in tests)
        return IntegrationValidationResult(passed, refs, tuple(reports),
            dirty or "\n".join(item.evidence_ref for item in reports if item.status != "passed"),
            tuple(node_execution))
