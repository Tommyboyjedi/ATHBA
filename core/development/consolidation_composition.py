"""Compose the optional checkpoint entirely from existing development capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.completed_req_consolidation import CompletedReqConsolidation, ConsolidationDependencies
from core.development.consolidation_git import ConsolidationGit
from core.development.consolidation_language import ConsolidationLanguage
from core.development.consolidation_material import ConsolidationMaterial, ConsolidationMaterialDependencies
from core.development.consolidation_reasoning import ConsolidationReasoning
from core.development.consolidation_validation import ConsolidationValidation, ConsolidationValidationDependencies
from core.development.deterministic_regression import DeterministicRegressionService
from core.development.microcycle_domain import LanguageTestAdapter
from core.development.production_reduction import ProductionChangeReducer, ProductionReductionDependencies
from core.development.production_reduction_acceptance import CompletionReductionVerifier
from core.development.production_reduction_syntax import ProductionReductionAdapter
from core.development.project_environment_port import PreparedProjectEnvironment
from core.development.test_material import TestMaterialAdapter
from core.execution.reasoning_gateway import ReasoningGateway


@dataclass(frozen=True)
class ConsolidationCompositionRequest:
    state_root: Path
    repository_root: Path
    environment: PreparedProjectEnvironment
    adapter: LanguageTestAdapter
    syntax: ProductionReductionAdapter
    tests: TestMaterialAdapter
    regression: DeterministicRegressionService
    reasoning: ReasoningGateway


def compose_consolidation(request: ConsolidationCompositionRequest) -> CompletedReqConsolidation:
    language = ConsolidationLanguage(request.adapter, request.tests)
    git = ConsolidationGit(request.repository_root, request.tests)
    reducer = ProductionChangeReducer(ProductionReductionDependencies(
        request.state_root / "consolidation-reductions", request.syntax,
        request.regression, CompletionReductionVerifier(request.adapter)))
    material = ConsolidationMaterial(ConsolidationMaterialDependencies(
        request.repository_root, MicrocycleStateRepo(request.state_root / "microcycles"),
        ScenarioDraftStateRepo(request.state_root / "scenario-drafts"), request.tests, language))
    validation = ConsolidationValidation(ConsolidationValidationDependencies(
        git, language, request.tests, request.regression, reducer))
    return CompletedReqConsolidation(ConsolidationDependencies(
        request.state_root / "evidence-consolidations", material, ConsolidationReasoning(request.reasoning),
        language, request.tests, git, validation, request.environment))
