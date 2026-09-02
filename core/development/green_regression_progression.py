from __future__ import annotations

from dataclasses import dataclass

from core.development.green_regression_domain import RegressionDisposition, RegressionGateResult
from core.development.python_test_runtime import PythonPytestRuntime
from core.development.tdd_progression import BehaviorContract, BehaviorContractRunState, ContractCycleRecord
from core.development.tdd_progression_validation import require_text
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult

REGRESSION_GATE_WORK_UNIT_SUFFIX = "--regression"
REGRESSION_REPAIR_WORK_UNIT_SUFFIX = "--regression-repair"
REGRESSION_PROBE_WORK_UNIT_PREFIX = "--regression-probe-"
INFRASTRUCTURE_TOKENS = (
    "transport",
    "environment",
    "pytest is unavailable",
    "bootstrap",
    "error collecting",
    "modulenotfounderror",
    "importerror",
)


@dataclass(frozen=True)
class RegressionGateRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState
    cycle: ContractCycleRecord


@dataclass(frozen=True)
class RegressionRepairWorkUnitBuildRequest:
    contract: BehaviorContract
    cycle: ContractCycleRecord
    regression_result: RegressionGateResult


@dataclass(frozen=True)
class RegressionGateWorkUnitBuildRequest:
    step_id: str
    production_path: str
    target_test_name: str
    suite_test_names: list[str]


@dataclass(frozen=True)
class RegressionDiagnosticWorkUnitBuildRequest:
    step_id: str
    production_path: str
    test_name: str
    probe_index: int


class RegressionGateWorkUnitFactory:
    def __init__(self, runtime: PythonPytestRuntime | None = None):
        self.runtime = runtime or PythonPytestRuntime()

    def build(self, request: RegressionGateWorkUnitBuildRequest) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=f"{request.step_id}{REGRESSION_GATE_WORK_UNIT_SUFFIX}",
            project_id="regression-gate",
            parent_ticket_id=request.step_id,
            objective=(
                "ATHBA supervisory regression gate. Do not modify files. "
                "Confirm the focused target test still passes and then run the full accepted regression suite."
            ),
            allowed_paths=[request.production_path],
            acceptance=AcceptanceContract(
                commands=[
                    self.runtime.pytest_command(request.target_test_name),
                    self.runtime.pytest_targets_command(request.suite_test_names),
                ],
                required_artifacts=[request.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class RegressionDiagnosticWorkUnitFactory:
    def __init__(self, runtime: PythonPytestRuntime | None = None):
        self.runtime = runtime or PythonPytestRuntime()

    def build(self, request: RegressionDiagnosticWorkUnitBuildRequest) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=f"{request.step_id}{REGRESSION_PROBE_WORK_UNIT_PREFIX}{request.probe_index}",
            project_id="regression-diagnostic",
            parent_ticket_id=request.step_id,
            objective="ATHBA regression diagnostic. Do not modify files. Run exactly one accepted test node.",
            allowed_paths=[request.production_path],
            acceptance=AcceptanceContract(
                commands=[self.runtime.pytest_command(request.test_name)],
                required_artifacts=[request.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class RegressionRepairWorkUnitFactory:
    def __init__(self, runtime: PythonPytestRuntime | None = None):
        self.runtime = runtime or PythonPytestRuntime()

    def build(self, request: RegressionRepairWorkUnitBuildRequest) -> DevelopmentWorkUnit:
        attempt = request.cycle.regression_repair_attempts + 1
        result = request.regression_result
        return DevelopmentWorkUnit(
            id=f"{request.cycle.step.step_id}{REGRESSION_REPAIR_WORK_UNIT_SUFFIX}-{attempt}",
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=(
                "Act in ATHBA's Developer role during bounded regression repair. "
                f"Work only within {request.cycle.step.production_path}. Do not edit tests. "
                f"Preserve the newly passing target test {result.target_test_name} while restoring these previously accepted tests: {', '.join(result.failing_prior_test_names)}. "
                "Make the smallest coherent production change necessary. Do not add unrelated behavior, extra tests, files, dependencies, or speculative abstractions."
            ),
            allowed_paths=[request.cycle.step.production_path],
            acceptance=AcceptanceContract(
                commands=[self.runtime.pytest_command(name) for name in result.conflict_test_names()],
                required_artifacts=[request.cycle.step.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class RegressionGateService:
    def __init__(self, gateway: WorkUnitExecutionGateway):
        self.gateway = gateway
        self.gate_factory = RegressionGateWorkUnitFactory()
        self.diagnostic_factory = RegressionDiagnosticWorkUnitFactory()

    async def evaluate(self, request: RegressionGateRequest) -> RegressionGateResult:
        candidate_revision = _candidate_revision(request.cycle)
        suite_test_names = _suite_test_names(request.run_state.accepted_green_test_names, request.cycle.step.test_name)
        outcome = await self.gateway.execute(
            self.gate_factory.build(
                RegressionGateWorkUnitBuildRequest(
                    step_id=request.cycle.step.step_id,
                    production_path=request.cycle.step.production_path,
                    target_test_name=request.cycle.step.test_name,
                    suite_test_names=suite_test_names,
                )
            ),
            request.run_state.repository_binding.with_base_sha(candidate_revision),
        )
        if outcome.accepted:
            return RegressionGateResult(
                candidate_revision=candidate_revision,
                target_test_name=request.cycle.step.test_name,
                suite_test_names=suite_test_names,
                target_test_passed=True,
                complete_suite_passed=True,
                failing_prior_test_names=[],
                passing_prior_test_names=[name for name in suite_test_names if name != request.cycle.step.test_name],
                evidence_refs=_evidence_refs([outcome]),
                stdout=outcome.stdout,
                stderr=outcome.stderr,
                disposition=RegressionDisposition.REGRESSION_CLEAR.value,
            )
        if _is_infrastructure_result(outcome):
            return RegressionGateResult(
                candidate_revision=candidate_revision,
                target_test_name=request.cycle.step.test_name,
                suite_test_names=suite_test_names,
                target_test_passed=False,
                complete_suite_passed=False,
                failing_prior_test_names=[],
                passing_prior_test_names=[],
                evidence_refs=_evidence_refs([outcome]),
                stdout=outcome.stdout,
                stderr=outcome.stderr,
                disposition=RegressionDisposition.REGRESSION_INFRASTRUCTURE_FAILURE.value,
            )
        diagnostics = await self._diagnose(request, suite_test_names)
        if any(_is_infrastructure_result(result) for result in diagnostics.values()):
            return RegressionGateResult(
                candidate_revision=candidate_revision,
                target_test_name=request.cycle.step.test_name,
                suite_test_names=suite_test_names,
                target_test_passed=bool(diagnostics[request.cycle.step.test_name].accepted),
                complete_suite_passed=False,
                failing_prior_test_names=[],
                passing_prior_test_names=[],
                evidence_refs=_evidence_refs([outcome, *diagnostics.values()]),
                stdout=outcome.stdout,
                stderr=outcome.stderr,
                disposition=RegressionDisposition.REGRESSION_INFRASTRUCTURE_FAILURE.value,
            )
        failing_prior = [name for name in suite_test_names if name != request.cycle.step.test_name and not diagnostics[name].accepted]
        passing_prior = [name for name in suite_test_names if name != request.cycle.step.test_name and diagnostics[name].accepted]
        return RegressionGateResult(
            candidate_revision=candidate_revision,
            target_test_name=request.cycle.step.test_name,
            suite_test_names=suite_test_names,
            target_test_passed=bool(diagnostics[request.cycle.step.test_name].accepted),
            complete_suite_passed=False,
            failing_prior_test_names=failing_prior,
            passing_prior_test_names=passing_prior,
            evidence_refs=_evidence_refs([outcome, *diagnostics.values()]),
            stdout=outcome.stdout,
            stderr=outcome.stderr,
            disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
        )

    async def _diagnose(
        self,
        request: RegressionGateRequest,
        suite_test_names: list[str],
    ) -> dict[str, WorkUnitExecutionResult]:
        candidate_revision = _candidate_revision(request.cycle)
        binding = request.run_state.repository_binding.with_base_sha(candidate_revision)
        results: dict[str, WorkUnitExecutionResult] = {}
        for index, test_name in enumerate(suite_test_names, start=1):
            work_unit = self.diagnostic_factory.build(
                RegressionDiagnosticWorkUnitBuildRequest(
                    step_id=request.cycle.step.step_id,
                    production_path=request.cycle.step.production_path,
                    test_name=test_name,
                    probe_index=index,
                )
            )
            results[test_name] = await self.gateway.execute(work_unit, binding)
        return results


def _candidate_revision(cycle: ContractCycleRecord) -> str:
    require_text(cycle.candidate_revision or "", "regression candidate revision")
    return cycle.candidate_revision or ""


def _suite_test_names(accepted_green_test_names: list[str], target_test_name: str) -> list[str]:
    names = [*accepted_green_test_names, target_test_name]
    unique: list[str] = []
    for name in names:
        if name not in unique:
            unique.append(name)
    return unique


def _evidence_refs(results: list[WorkUnitExecutionResult]) -> list[str]:
    refs: list[str] = []
    for result in results:
        if result.evidence_location and result.evidence_location not in refs:
            refs.append(result.evidence_location)
    return refs


def _is_infrastructure_result(result: WorkUnitExecutionResult) -> bool:
    status = (result.status or "").lower()
    detail = " ".join(item for item in [result.error, result.stderr, result.stdout, status] if item).lower()
    return status in {"transport_error", "failed"} or any(token in detail for token in INFRASTRUCTURE_TOKENS)
