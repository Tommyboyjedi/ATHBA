"""Execute approved replacement evidence before reusing bounded production reduction."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
import time

from core.atomic_json_file import read_json_file
from core.development.consolidation_git import ConsolidationGit
from core.development.consolidation_journal import ConsolidationJournal
from core.development.consolidation_language import ConsolidationLanguage, ConsolidationTestSource
from core.development.consolidation_material import SelectedConsolidation
from core.development.deterministic_regression import (
    DeterministicRegressionService, REGRESSION_CLEAR, REGRESSION_INFRASTRUCTURE_FAILURE,
)
from core.development.microcycle_domain import RegressionContractRequest, RegressionState
from core.development.production_reduction import ProductionChangeReducer
from core.development.production_reduction_acceptance import (
    CompletionReductionVerifier, ReductionFrontierCheckRequest, verify_reduction_acceptance,
)
from core.development.production_reduction_domain import ConsolidatedReductionRequest
from core.development.test_material import TestMaterialAdapter, TestSourceRequest

INITIAL_VERIFICATION_SECONDS = 120.0


@dataclass(frozen=True)
class ConsolidationValidationDependencies:
    git: ConsolidationGit
    language: ConsolidationLanguage
    material: TestMaterialAdapter
    regression: DeterministicRegressionService
    reducer: ProductionChangeReducer


@dataclass(frozen=True)
class ConsolidationValidationInput:
    selection: SelectedConsolidation
    test_revision: str
    replacement_source: str


class ConsolidationValidation:
    """Reuse executed-test proof and regression; test failure never calls Developer."""

    def __init__(self, dependencies: ConsolidationValidationDependencies):
        self.dependencies = dependencies

    def request(self, value: ConsolidationValidationInput) -> ConsolidatedReductionRequest:
        deps = self.dependencies
        selected = value.selection
        context = selected.reasoning
        source = ConsolidationTestSource(context.checkpoint_id, context.replacement_test_name,
            value.replacement_source, selected.production_paths[0], value.test_revision)
        authorities = [deps.language.authority(source)]
        for name in selected.unaffected_tests:
            path = deps.material.test_path(name)
            module = deps.git.git.command(("show", f"{value.test_revision}:{path}"))
            test = deps.material.extract(TestSourceRequest(module, name))
            if test is None:
                raise ValueError("unaffected accepted test vanished during consolidation")
            authorities.append(deps.language.authority(ConsolidationTestSource(
                context.checkpoint_id, name, test, selected.production_paths[0], value.test_revision)))
        command = deps.language.adapter.regression_contract(
            RegressionContractRequest(deps.language.model(source))).command
        return ConsolidatedReductionRequest(
            deps.git.git.repository_root, context.checkpoint_id,
            selected.scope.windows[0].before_revision, value.test_revision,
            selected.production_paths, tuple(authorities), command, selected.unaffected_tests,
            deps.language.adapter.descriptor.adapter_id, RegressionState("not_checked", command),
            selected.production_paths, selected.scope,
        )

    def accept(self, request: ConsolidatedReductionRequest,
               journal: ConsolidationJournal) -> RegressionState | None:
        path = journal.root / "test-acceptance.json"
        if path.exists():
            evidence = read_json_file(path)
            if evidence["test_revision"] != request.tests_revision:
                raise ValueError("consolidation execution authority changed")
            return RegressionState.from_dict(evidence["regression"]) if evidence["accepted"] else None
        deps = self.dependencies
        with deps.git.git.test_workspace(request.tests_revision) as workspace:
            observed, result = verify_reduction_acceptance(
                ReductionFrontierCheckRequest(request, workspace, time.monotonic() + INITIAL_VERIFICATION_SECONDS),
                (CompletionReductionVerifier(deps.language.adapter), deps.regression))
            deps.git.assert_trial_unchanged(workspace)
        if result.status == REGRESSION_INFRASTRUCTURE_FAILURE:
            raise ValueError("consolidation execution infrastructure is uncertain")
        regression = result.state(request.regression_command)
        journal.record(("test-acceptance.json", {
            "test_revision": request.tests_revision, "unchanged_production": True,
            "accepted": result.status == REGRESSION_CLEAR,
            "executed_tests": asdict(observed), "regression": regression.to_dict(),
        }))
        return regression if result.status == REGRESSION_CLEAR else None

    def reduce(self, request: ConsolidatedReductionRequest, regression: RegressionState):
        return self.dependencies.reducer.reduce(replace(request, initial_regression=regression))
