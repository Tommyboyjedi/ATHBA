import json
from dataclasses import replace

import pytest

from core.development.behavior_contract_coordinator import (
    BehaviorContractCoordinator,
    ContractDeveloperWorkUnitFactory,
    WorkUnitBuildRequest,
)
from core.development.green_regression_domain import RegressionDisposition, RegressionGateResult
from core.development.green_regression_progression import REGRESSION_GATE_WORK_UNIT_SUFFIX
from core.development.semantic_progression_domain import (
    OpenSemanticObligation,
    ProvisionalRequirementState,
    SemanticProgressLedger,
)
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRunState,
    ContractCycleRecord,
    SemanticReviewResult,
    TddPhase,
    TddPhaseState,
    TddSnapshot,
    TddStepProposal,
)
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class FakeReasoningGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, dict):
            return ReasoningResult(text=json.dumps(response), provider="fake", model="fake-model")
        return ReasoningResult(text=response, provider="fake", model="fake-model")


class FakeExecutionGateway:
    def __init__(self, results):
        self.results = dict(results)
        self.calls = []

    async def execute(self, work_unit, repository_binding):
        self.calls.append(
            {
                "id": work_unit.id,
                "base_sha": repository_binding.base_sha,
                "commands": work_unit.acceptance.commands,
                "objective": work_unit.objective,
            }
        )
        result = self.results.get(work_unit.id)
        if result is None and work_unit.id.endswith(REGRESSION_GATE_WORK_UNIT_SUFFIX):
            return accepted(work_unit.id, repository_binding.base_sha or "d" * 40)
        if result is None:
            raise KeyError(work_unit.id)
        if isinstance(result, list):
            if not result:
                raise AssertionError(f"no more results configured for {work_unit.id}")
            return result.pop(0)
        return result


class MemoryStateRepo:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot
        self.saved = []

    def load(self, project_id: str):
        return self.snapshot

    def save(self, snapshot: TddSnapshot):
        self.snapshot = snapshot
        self.saved.append(snapshot)
        return snapshot


class StaticReviewMaterialProvider:
    def __init__(self, text: str):
        self.text = text

    def render(self, request):
        return self.text


def binding(base_sha="a" * 40):
    return RepositoryBinding(
        repository_id="toy-fixture",
        base_ref="main",
        base_sha=base_sha,
        registered_root=None,
    )


def contract_payload(*, contract_id: str, project_id: str, component_name: str, requirement_ref: str, source_ref: str, production_path: str, test_path: str, test_hint: str):
    return {
        "id": contract_id,
        "project_id": project_id,
        "component_name": component_name,
        "capability": f"Manage {component_name} behavior.",
        "requirement_source": f"Build {component_name}.",
        "source_clauses": [{"ref": source_ref, "text": f"{component_name} supports {test_hint}.", "kind": "behavior"}],
        "observable_requirements": [
            {
                "ref": requirement_ref,
                "source_refs": [source_ref],
                "summary": f"{component_name} supports {test_hint}.",
                "observable_outcome": f"{test_hint} is externally visible.",
                "test_hint": test_hint,
                "error_expectation": None,
                "preserves_state_on_failure": True,
                "depends_on": [],
            }
        ],
        "invariants": [f"{component_name} stays small and direct"],
        "production_paths": [production_path],
        "test_paths": [test_path],
        "public_api": [f"{component_name}.run()"],
        "error_semantics": [],
        "non_goals": ["no persistence"],
        "completion_criteria": ["accepted tests cover the requirement"],
        "status": "tdd_ready",
    }


def reservation_contract() -> BehaviorContract:
    return BehaviorContract.from_dict(
        contract_payload(
            contract_id="contract-reservation-book",
            project_id="reservation-book",
            component_name="ReservationBook",
            requirement_ref="RB-1",
            source_ref="SRC-RB-1",
            production_path="reservation_book.py",
            test_path="tests/test_reservation_book.py",
            test_hint="test_add_resource_sets_availability",
        )
    )


def catalog_contract() -> BehaviorContract:
    return BehaviorContract.from_dict(
        contract_payload(
            contract_id="contract-catalog",
            project_id="catalog",
            component_name="Catalog",
            requirement_ref="CAT-1",
            source_ref="SRC-CAT-1",
            production_path="catalog.py",
            test_path="tests/test_catalog.py",
            test_hint="test_add_title_records_lookup",
        )
    )


def proposal(*, step_id="step-1", requirement_ref="RB-1", production_path="reservation_book.py", test_path="tests/test_reservation_book.py", test_name="tests/test_reservation_book.py::test_add_resource_sets_availability", behavior="Adding a resource reports capacity."):
    return TddStepProposal(
        step_id=step_id,
        requirement_refs=[requirement_ref],
        focused_behavior=behavior,
        test_name=test_name,
        expected_result=f"{test_name} passes.",
        test_path=test_path,
        production_path=production_path,
        red_objective=f"Add a failing pytest proving {behavior}",
        green_objective=f"Implement only enough code for {behavior}",
        reason_next_smallest=f"{behavior} is the next smallest slice.",
    )


def green_cycle(step: TddStepProposal, *, base_revision: str, candidate_revision: str, pool: str = "review_ready") -> ContractCycleRecord:
    return replace(
        ContractCycleRecord.from_step(step, base_revision=base_revision),
        green_phase=TddPhaseState(
            phase=TddPhase.GREEN.value,
            work_unit_id=f"{step.step_id}--green",
            status="checks_passed",
            accepted_revision=candidate_revision,
            change_id=f"change-{step.step_id}--green",
            evidence_location=f"/tmp/{step.step_id}--green.json",
        ),
        candidate_revision=candidate_revision,
        pool=pool,
    )


def accepted(work_unit_id: str, revision: str, *, stdout: str | None = None, stderr: str | None = None):
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=True,
        status="checks_passed",
        accepted_revision=revision,
        change_id=f"change-{work_unit_id}",
        evidence_location=f"/tmp/{work_unit_id}.json",
        stdout=stdout,
        stderr=stderr,
    )


def rejected(work_unit_id: str, *, status="checks_failed", error="acceptance failed", stdout: str | None = None, stderr: str | None = None):
    return WorkUnitExecutionResult(
        work_unit_id=work_unit_id,
        accepted=False,
        status=status,
        change_id=f"change-{work_unit_id}",
        evidence_location=f"/tmp/{work_unit_id}.json",
        error=error,
        stdout=stdout,
        stderr=stderr,
    )


def run_state(contract: BehaviorContract, *, current_pool="review_ready", cycles=None, semantic_base_revision="a" * 40, development_base_revision=None, accepted_green_test_names=None, semantic_progress=None):
    development_base_revision = development_base_revision or semantic_base_revision
    return BehaviorContractRunState(
        contract=contract,
        repository_binding=binding(development_base_revision),
        semantic_base_revision=semantic_base_revision,
        development_base_revision=development_base_revision,
        current_pool=current_pool,
        accepted_green_test_names=list(accepted_green_test_names or []),
        cycles=list(cycles or []),
        semantic_progress=semantic_progress or SemanticProgressLedger(),
    )


def snapshot_for(contract: BehaviorContract, run_state_value: BehaviorContractRunState) -> TddSnapshot:
    return TddSnapshot(
        project_id=contract.project_id,
        repository_binding=run_state_value.repository_binding,
        current_trusted_revision=run_state_value.development_base_revision,
        development_base_revision=run_state_value.development_base_revision,
        semantic_base_revision=run_state_value.semantic_base_revision,
        contract_runs={contract.id: run_state_value},
    )


def coordinator(contract: BehaviorContract, snapshot: TddSnapshot, gateway: FakeExecutionGateway, reasoner: FakeReasoningGateway, *, max_regression_repairs: int = 2):
    return BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=snapshot.repository_binding,
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
        max_regression_repairs=max_regression_repairs,
    )


def approved_review(candidate_revision: str, step_id: str):
    return {
        "verdict": "approved",
        "rationale": "Looks correct.",
        "findings": ["clean"],
        "candidate_revision": candidate_revision,
        "step_id": step_id,
        "evidence_refs": ["review:1"],
        "repair_instructions": [],
    }


def planner_complete():
    return {"status": "complete", "rationale": "Done.", "proposal": None, "completed_requirement_refs": []}


@pytest.mark.asyncio
async def test_developer_acceptance_stays_single_test_for_catalog_domain():
    step = proposal(
        requirement_ref="CAT-1",
        production_path="catalog.py",
        test_path="tests/test_catalog.py",
        test_name="tests/test_catalog.py::test_add_title_records_lookup",
        behavior="Adding a title records a lookup entry.",
    )
    built = ContractDeveloperWorkUnitFactory().build(WorkUnitBuildRequest(catalog_contract(), step))
    assert built.acceptance.commands == [["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", step.test_name]]
    assert "Do not attempt to make the entire suite pass" in built.objective


@pytest.mark.asyncio
async def test_green_promotion_requires_separate_regression_gate_pass():
    contract = reservation_contract()
    step = proposal()
    cycle = green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40)
    state = run_state(contract, cycles=[cycle], semantic_base_revision="a" * 40)
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway({})
    reasoner = FakeReasoningGateway([approved_review("b" * 40, step.step_id), planner_complete()])

    result = await coordinator(contract, snapshot, gateway, reasoner).run_contract(contract)

    assert gateway.calls[0]["id"] == f"{step.step_id}--regression"
    assert result.current_binding.base_sha == "b" * 40


@pytest.mark.asyncio
async def test_accumulated_regression_blocks_promotion_and_is_persisted():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    cycle = green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40)
    state = run_state(
        contract,
        cycles=[cycle],
        semantic_base_revision="a" * 40,
        accepted_green_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
    )
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway(
        {
            f"{step.step_id}--regression": rejected(f"{step.step_id}--regression"),
            f"{step.step_id}--regression-probe-1": rejected(f"{step.step_id}--regression-probe-1"),
            f"{step.step_id}--regression-probe-2": accepted(f"{step.step_id}--regression-probe-2", "b" * 40),
        }
    )
    reasoner = FakeReasoningGateway([])
    repo = MemoryStateRepo(snapshot)

    coordinator_instance = BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=snapshot.repository_binding,
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    )
    advanced = await coordinator_instance.review_progressor.advance(state)
    regression = advanced.run_state.current_cycle().regression_result

    assert advanced.run_state.current_pool == "repair_ready"
    assert advanced.run_state.development_base_revision == "a" * 40
    assert regression is not None
    assert regression.disposition == RegressionDisposition.ACCUMULATED_REGRESSION.value
    assert regression.failing_prior_test_names == ["tests/test_reservation_book.py::test_existing_behavior"]


@pytest.mark.asyncio
async def test_regression_repair_packet_is_bounded_to_target_and_failures():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    regression = RegressionGateResult(
        candidate_revision="b" * 40,
        target_test_name=step.test_name,
        suite_test_names=[
            "tests/test_reservation_book.py::test_existing_behavior",
            "tests/test_reservation_book.py::test_unrelated_behavior",
            step.test_name,
        ],
        target_test_passed=True,
        complete_suite_passed=False,
        failing_prior_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
        passing_prior_test_names=["tests/test_reservation_book.py::test_unrelated_behavior"],
        disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
    )
    cycle = replace(green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40, pool="repair_ready"), regression_result=regression)
    state = run_state(contract, current_pool="repair_ready", cycles=[cycle], accepted_green_test_names=regression.suite_test_names[:-1])
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway({f"{step.step_id}--regression-repair-1": rejected(f"{step.step_id}--regression-repair-1")})
    reasoner = FakeReasoningGateway([])

    result = await coordinator(contract, snapshot, gateway, reasoner).run_contract(contract)

    assert gateway.calls[0]["id"] == f"{step.step_id}--regression-repair-1"
    assert gateway.calls[0]["commands"] == [
        ["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", step.test_name],
        ["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_reservation_book.py::test_existing_behavior"],
    ]
    assert result.current_pool == "replan_ready"


@pytest.mark.asyncio
async def test_regression_repair_success_reruns_full_gate_before_promotion():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    regression = RegressionGateResult(
        candidate_revision="b" * 40,
        target_test_name=step.test_name,
        suite_test_names=["tests/test_reservation_book.py::test_existing_behavior", step.test_name],
        target_test_passed=True,
        complete_suite_passed=False,
        failing_prior_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
        disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
    )
    cycle = replace(green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40, pool="repair_ready"), regression_result=regression)
    state = run_state(contract, current_pool="repair_ready", cycles=[cycle], semantic_base_revision="a" * 40, accepted_green_test_names=["tests/test_reservation_book.py::test_existing_behavior"])
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway({f"{step.step_id}--regression-repair-1": accepted(f"{step.step_id}--regression-repair-1", "c" * 40)})
    reasoner = FakeReasoningGateway([approved_review("c" * 40, step.step_id), planner_complete()])

    result = await coordinator(contract, snapshot, gateway, reasoner).run_contract(contract)

    assert [call["id"] for call in gateway.calls[:2]] == [f"{step.step_id}--regression-repair-1", f"{step.step_id}--regression"]
    assert result.current_binding.base_sha == "c" * 40


@pytest.mark.asyncio
async def test_second_regression_updates_conflict_set_after_local_repair():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    regression = RegressionGateResult(
        candidate_revision="b" * 40,
        target_test_name=step.test_name,
        suite_test_names=[
            "tests/test_reservation_book.py::test_existing_behavior",
            "tests/test_reservation_book.py::test_unrelated_behavior",
            step.test_name,
        ],
        target_test_passed=True,
        complete_suite_passed=False,
        failing_prior_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
        passing_prior_test_names=["tests/test_reservation_book.py::test_unrelated_behavior"],
        disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
    )
    cycle = replace(green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40, pool="repair_ready"), regression_result=regression)
    state = run_state(contract, current_pool="repair_ready", cycles=[cycle], accepted_green_test_names=regression.suite_test_names[:-1])
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway(
        {
            f"{step.step_id}--regression-repair-1": accepted(f"{step.step_id}--regression-repair-1", "c" * 40),
            f"{step.step_id}--regression": rejected(f"{step.step_id}--regression"),
            f"{step.step_id}--regression-probe-1": accepted(f"{step.step_id}--regression-probe-1", "c" * 40),
            f"{step.step_id}--regression-probe-2": rejected(f"{step.step_id}--regression-probe-2"),
            f"{step.step_id}--regression-probe-3": accepted(f"{step.step_id}--regression-probe-3", "c" * 40),
        }
    )
    reasoner = FakeReasoningGateway([])
    repo = MemoryStateRepo(snapshot)

    coordinator_instance = BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=snapshot.repository_binding,
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    )
    repaired = await coordinator_instance.repair_progressor.advance(state)
    rerouted = await coordinator_instance.review_progressor.advance(repaired.run_state)
    regression_after = rerouted.run_state.current_cycle().regression_result

    assert rerouted.run_state.current_pool == "repair_ready"
    assert regression_after is not None
    assert regression_after.failing_prior_test_names == ["tests/test_reservation_book.py::test_unrelated_behavior"]


@pytest.mark.asyncio
async def test_regression_repair_retry_exhaustion_keeps_previous_development_base():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    regression = RegressionGateResult(
        candidate_revision="b" * 40,
        target_test_name=step.test_name,
        suite_test_names=["tests/test_reservation_book.py::test_existing_behavior", step.test_name],
        target_test_passed=True,
        complete_suite_passed=False,
        failing_prior_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
        disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
    )
    cycle = replace(green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40, pool="repair_ready"), regression_result=regression)
    state = run_state(contract, current_pool="repair_ready", cycles=[cycle], semantic_base_revision="a" * 40)
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway(
        {
            f"{step.step_id}--regression-repair-1": rejected(f"{step.step_id}--regression-repair-1", error="still broken"),
            f"{step.step_id}--regression-repair-2": rejected(f"{step.step_id}--regression-repair-2", error="still broken"),
        }
    )
    reasoner = FakeReasoningGateway([])

    result = await coordinator(contract, snapshot, gateway, reasoner, max_regression_repairs=2).run_contract(contract)

    assert result.current_pool == "replan_ready"
    assert result.current_binding.base_sha == "a" * 40


@pytest.mark.asyncio
async def test_provisional_green_tests_remain_regression_authority_for_catalog_domain():
    contract = catalog_contract()
    step = proposal(
        requirement_ref="CAT-1",
        production_path="catalog.py",
        test_path="tests/test_catalog.py",
        test_name="tests/test_catalog.py::test_remove_title_updates_lookup",
        behavior="Removing a title updates the lookup.",
    )
    ledger = SemanticProgressLedger(
        provisional_requirements=[
            ProvisionalRequirementState(
                requirement_ref="CAT-0",
                development_revision="a" * 40,
                originating_step_id="step-cat-0",
                accepted_test_names=["tests/test_catalog.py::test_add_title_records_lookup"],
                open_obligation_ids=["cat-open-1"],
            )
        ],
        open_obligations=[
            OpenSemanticObligation(
                obligation_id="cat-open-1",
                owning_requirement_ref="CAT-0",
                blocking_requirement_refs=["CAT-1"],
                rationale="Follow-up semantics.",
                evidence_refs=["review:0"],
                originating_step_id="step-cat-0",
                introduced_revision="a" * 40,
            )
        ],
    )
    cycle = green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40)
    state = run_state(
        contract,
        cycles=[cycle],
        accepted_green_test_names=["tests/test_catalog.py::test_add_title_records_lookup"],
        semantic_progress=ledger,
    )
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway({})
    reasoner = FakeReasoningGateway([])
    coordinator_instance = BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=snapshot.repository_binding,
        state_repo=MemoryStateRepo(snapshot),
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    )

    await coordinator_instance.review_progressor.advance(state)

    assert gateway.calls[0]["commands"] == [
        ["python3", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", step.test_name],
        [
            "python3",
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_catalog.py::test_add_title_records_lookup",
            step.test_name,
        ],
    ]


@pytest.mark.asyncio
async def test_resume_from_detected_regression_starts_with_regression_repair():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    regression = RegressionGateResult(
        candidate_revision="b" * 40,
        target_test_name=step.test_name,
        suite_test_names=["tests/test_reservation_book.py::test_existing_behavior", step.test_name],
        target_test_passed=True,
        complete_suite_passed=False,
        failing_prior_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
        disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
    )
    cycle = replace(green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40, pool="repair_ready"), regression_result=regression)
    state = run_state(contract, current_pool="repair_ready", cycles=[cycle], accepted_green_test_names=["tests/test_reservation_book.py::test_existing_behavior"])
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway({f"{step.step_id}--regression-repair-1": accepted(f"{step.step_id}--regression-repair-1", "c" * 40)})
    reasoner = FakeReasoningGateway([approved_review("c" * 40, step.step_id), planner_complete()])

    await coordinator(contract, snapshot, gateway, reasoner).run_contract(contract)

    assert gateway.calls[0]["id"] == f"{step.step_id}--regression-repair-1"


@pytest.mark.asyncio
async def test_regression_gate_infrastructure_failure_stays_distinct_and_fails_closed():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    cycle = green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40)
    state = run_state(contract, cycles=[cycle], semantic_base_revision="a" * 40, accepted_green_test_names=["tests/test_reservation_book.py::test_existing_behavior"])
    snapshot = snapshot_for(contract, state)
    gateway = FakeExecutionGateway(
        {
            f"{step.step_id}--regression": rejected(
                f"{step.step_id}--regression",
                status="transport_error",
                error="pytest is unavailable",
                stdout="bootstrap failed",
                stderr="ImportError: missing dependency",
            )
        }
    )
    reasoner = FakeReasoningGateway([])
    repo = MemoryStateRepo(snapshot)

    result = await BehaviorContractCoordinator(
        execution_gateway=gateway,
        reasoning_gateway=reasoner,
        repository_binding=snapshot.repository_binding,
        state_repo=repo,
        review_material_provider=StaticReviewMaterialProvider("candidate source"),
    ).run_contract(contract)
    regression = repo.snapshot.contract_runs[contract.id].current_cycle().regression_result

    assert result.current_pool == "replan_ready"
    assert result.current_binding.base_sha == "a" * 40
    assert regression is not None
    assert regression.disposition == RegressionDisposition.REGRESSION_INFRASTRUCTURE_FAILURE.value


def test_regression_resume_state_round_trip_preserves_conflict_set():
    contract = reservation_contract()
    step = proposal(test_name="tests/test_reservation_book.py::test_new_behavior")
    cycle = replace(
        green_cycle(step, base_revision="a" * 40, candidate_revision="b" * 40, pool="repair_ready"),
        regression_result=RegressionGateResult(
            candidate_revision="b" * 40,
            target_test_name=step.test_name,
            suite_test_names=["tests/test_reservation_book.py::test_existing_behavior", step.test_name],
            target_test_passed=True,
            complete_suite_passed=False,
            failing_prior_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
            disposition=RegressionDisposition.ACCUMULATED_REGRESSION.value,
        ),
        regression_repair_attempts=1,
    )
    state = run_state(
        contract,
        current_pool="repair_ready",
        cycles=[cycle],
        accepted_green_test_names=["tests/test_reservation_book.py::test_existing_behavior"],
    )

    restored = BehaviorContractRunState.from_dict(state.to_dict())

    assert restored.current_pool == "repair_ready"
    assert restored.accepted_green_test_names == ["tests/test_reservation_book.py::test_existing_behavior"]
    assert restored.current_cycle().regression_result is not None
    assert restored.current_cycle().regression_result.failing_prior_test_names == ["tests/test_reservation_book.py::test_existing_behavior"]
    assert restored.current_cycle().regression_repair_attempts == 1
