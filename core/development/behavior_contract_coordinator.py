"""Contract-driven TDD lane for PR16 behavior-contract orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.tdd_coordinator import (
    RED_ALREADY_SATISFIED_FRAGMENT,
    TddStateRepository,
    _PhaseOutcome,
    _blocked_reason_for_result,
    _is_red_already_satisfied,
    _phase_state_from_result,
)
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRunState,
    CONTRACT_POOL_STATUSES,
    ContractCycleRecord,
    SemanticReviewResult,
    TddPhase,
    TddSnapshot,
    TddStepDecision,
    TddStepProposal,
    green_work_unit_id,
    red_work_unit_id,
    repair_work_unit_id,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest
from core.execution.work_unit_gateway import WorkUnitExecutionGateway


@dataclass(frozen=True)
class BehaviorContractCoordinationResult:
    contract_id: str
    current_binding: RepositoryBinding
    semantic_revision: str | None
    current_pool: str
    cycles: list[ContractCycleRecord]
    completed_requirement_refs: list[str]
    blocked_reason: str | None = None


class ReviewMaterialProvider(Protocol):
    def render(self, contract: BehaviorContract, run_state: BehaviorContractRunState, cycle: ContractCycleRecord) -> str:
        ...


class BehaviorContractPlanner:
    """Turn one component requirement into a structured provider-neutral contract."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def create_contract(self, *, project_id: str, requirement_text: str) -> BehaviorContract:
        request = ReasoningRequest(
            purpose="athba_behavior_contract",
            prompt=_contract_prompt(project_id=project_id, requirement_text=requirement_text),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        return BehaviorContract.from_dict(_json_object(result.text, label="behavior contract"))


class DynamicTddPlanner:
    """Use reasoning to choose the next smallest useful RED step within a contract."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def decide_next_step(self, contract: BehaviorContract, run_state: BehaviorContractRunState) -> TddStepDecision:
        request = ReasoningRequest(
            purpose="athba_tdd_step_selection",
            prompt=_step_prompt(contract=contract, run_state=run_state),
            project_id=contract.project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        decision = TddStepDecision.from_dict(_json_object(result.text, label="step decision"))
        self._validate_decision(contract, run_state, decision)
        return decision

    def _validate_decision(
        self,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        decision: TddStepDecision,
    ) -> None:
        requirement_refs = set(contract.requirement_refs())
        completed_refs = set(run_state.completed_requirement_refs)
        if decision.status == "complete":
            if set(decision.completed_requirement_refs) != requirement_refs:
                raise ValueError("completion decisions must account for every contract requirement ref")
            return

        assert decision.proposal is not None
        proposal = decision.proposal
        if len(proposal.requirement_refs) != 1:
            raise ValueError("each TDD step proposal must target exactly one requirement ref")
        proposal_ref = proposal.requirement_refs[0]
        if proposal_ref not in requirement_refs:
            raise ValueError("step proposal referenced a requirement outside the contract")
        if proposal_ref in completed_refs:
            raise ValueError("step proposal repeated a requirement that is already semantically covered")
        if proposal.test_path not in contract.test_paths:
            raise ValueError("step proposal test path is outside the contract")
        if proposal.production_path not in contract.production_paths:
            raise ValueError("step proposal production path is outside the contract")


class SeniorReviewer:
    """Semantic gate that is separate from Rack AI mechanical acceptance."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def review(
        self,
        *,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        cycle: ContractCycleRecord,
        candidate_revision: str,
        review_material: str,
    ) -> SemanticReviewResult:
        request = ReasoningRequest(
            purpose="athba_senior_review",
            prompt=_review_prompt(
                contract=contract,
                run_state=run_state,
                cycle=cycle,
                candidate_revision=candidate_revision,
                review_material=review_material,
            ),
            project_id=contract.project_id,
            requires_large_context=True,
        )
        result = await self.gateway.reason(request)
        review = SemanticReviewResult.from_dict(_json_object(result.text, label="semantic review"))
        if review.candidate_revision != candidate_revision:
            raise ValueError("semantic review candidate revision mismatch")
        if review.step_id != cycle.step.step_id:
            raise ValueError("semantic review step id mismatch")
        return review


class ContractTesterWorkUnitFactory:
    def build(self, contract: BehaviorContract, step: TddStepProposal) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=red_work_unit_id(step.step_id),
            project_id=contract.project_id,
            parent_ticket_id=contract.id,
            objective=_tester_objective(contract, step),
            allowed_paths=[step.test_path],
            acceptance=AcceptanceContract(
                commands=[["python", "scripts/assert_test_fails.py", step.test_name, "expected failure"]],
                required_artifacts=[step.test_path],
            ),
            status=WorkUnitStatus.READY,
        )


class ContractDeveloperWorkUnitFactory:
    def build(self, contract: BehaviorContract, step: TddStepProposal) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=green_work_unit_id(step.step_id),
            project_id=contract.project_id,
            parent_ticket_id=contract.id,
            objective=_developer_objective(contract, step),
            allowed_paths=[step.production_path],
            acceptance=AcceptanceContract(
                commands=[["pytest", "-q", step.test_name], ["pytest", "-q", step.test_path]],
                required_artifacts=[step.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class ContractRepairWorkUnitFactory:
    def build(
        self,
        contract: BehaviorContract,
        cycle: ContractCycleRecord,
        review: SemanticReviewResult,
    ) -> DevelopmentWorkUnit:
        attempt_number = cycle.repair_attempts + 1
        return DevelopmentWorkUnit(
            id=repair_work_unit_id(cycle.step.step_id, attempt_number),
            project_id=contract.project_id,
            parent_ticket_id=contract.id,
            objective=_repair_objective(contract, cycle.step, review),
            allowed_paths=[cycle.step.production_path],
            acceptance=AcceptanceContract(
                commands=[["pytest", "-q", cycle.step.test_name], ["pytest", "-q", cycle.step.test_path]],
                required_artifacts=[cycle.step.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class BehaviorContractCoordinator:
    """Drive a contract through dynamic RED/GREEN cycles, review, and repair."""

    def __init__(
        self,
        *,
        execution_gateway: WorkUnitExecutionGateway,
        reasoning_gateway: ReasoningGateway,
        repository_binding: RepositoryBinding,
        state_repo: TddStateRepository | None = None,
        contract_planner: BehaviorContractPlanner | None = None,
        step_planner: DynamicTddPlanner | None = None,
        reviewer: SeniorReviewer | None = None,
        tester_factory: ContractTesterWorkUnitFactory | None = None,
        developer_factory: ContractDeveloperWorkUnitFactory | None = None,
        repair_factory: ContractRepairWorkUnitFactory | None = None,
        review_material_provider: ReviewMaterialProvider | None = None,
        max_semantic_repairs: int = 2,
    ):
        self.execution_gateway = execution_gateway
        self.reasoning_gateway = reasoning_gateway
        self.repository_binding = repository_binding
        self.state_repo = state_repo or TddStateRepo()
        self.contract_planner = contract_planner or BehaviorContractPlanner(reasoning_gateway)
        self.step_planner = step_planner or DynamicTddPlanner(reasoning_gateway)
        self.reviewer = reviewer or SeniorReviewer(reasoning_gateway)
        self.tester_factory = tester_factory or ContractTesterWorkUnitFactory()
        self.developer_factory = developer_factory or ContractDeveloperWorkUnitFactory()
        self.repair_factory = repair_factory or ContractRepairWorkUnitFactory()
        self.review_material_provider = review_material_provider
        self.max_semantic_repairs = max_semantic_repairs

    async def run_contract(self, contract: BehaviorContract) -> BehaviorContractCoordinationResult:
        project_id = contract.project_id
        snapshot = self.state_repo.load(project_id) or TddSnapshot(
            project_id=project_id,
            repository_binding=self.repository_binding,
            current_trusted_revision=self.repository_binding.base_sha,
        )
        run_state = snapshot.contract_runs.get(contract.id)
        if run_state is None:
            run_state = BehaviorContractRunState(
                contract=contract,
                repository_binding=self.repository_binding,
                semantic_base_revision=self.repository_binding.base_sha,
            )
            snapshot = self._save_run_state(snapshot, run_state)

        while True:
            if run_state.current_pool == "completed":
                return self._result_from_run_state(run_state)
            if run_state.current_pool == "replan_ready":
                return self._result_from_run_state(run_state)
            if run_state.current_pool in {"tdd_ready", "approved"}:
                decision = await self.step_planner.decide_next_step(contract, run_state)
                if decision.status == "complete":
                    run_state = replace(
                        run_state,
                        current_pool="completed",
                        completed_requirement_refs=decision.completed_requirement_refs,
                        contract=replace(contract, status="completed"),
                        repository_binding=run_state.repository_binding.with_base_sha(run_state.semantic_base_revision),
                    )
                    snapshot = self._save_run_state(snapshot, run_state)
                    return self._result_from_run_state(run_state)
                cycle = ContractCycleRecord.from_step(decision.proposal, base_revision=run_state.semantic_base_revision)
                run_state = replace(
                    run_state,
                    current_pool="cycle_active",
                    contract=replace(contract, status="cycle_active"),
                    cycles=[*run_state.cycles, cycle],
                )
                snapshot = self._save_run_state(snapshot, run_state)
                continue
            if run_state.current_pool == "cycle_active":
                cycle = run_state.current_cycle()
                if cycle is None:
                    raise ValueError("cycle_active run state requires an active cycle")
                if cycle.red_phase is not None and cycle.red_phase.accepted_revision is None:
                    red_outcome = await self._execute_phase(
                        phase=TddPhase.RED,
                        work_unit=self.tester_factory.build(contract, cycle.step),
                        base_binding=run_state.repository_binding.with_base_sha(run_state.semantic_base_revision),
                    )
                    if not red_outcome.accepted:
                        if _is_red_already_satisfied_from_phase(red_outcome):
                            run_state = replace(
                                run_state,
                                current_pool="tdd_ready",
                                contract=replace(contract, status="tdd_ready"),
                                blocked_reason="step already satisfied before RED",
                                cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, red_phase=red_outcome.phase_state, pool="approved")),
                            )
                            snapshot = self._save_run_state(snapshot, run_state)
                            continue
                        run_state = replace(
                            run_state,
                            current_pool="replan_ready",
                            contract=replace(contract, status="replan_ready"),
                            blocked_reason=red_outcome.blocked_reason,
                            cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, red_phase=red_outcome.phase_state, pool="replan_ready")),
                        )
                        snapshot = self._save_run_state(snapshot, run_state)
                        return self._result_from_run_state(run_state)
                    cycle = replace(cycle, red_phase=red_outcome.phase_state)
                    run_state = replace(run_state, cycles=self._replace_current_cycle(run_state.cycles, cycle))
                    snapshot = self._save_run_state(snapshot, run_state)
                if cycle.green_phase is not None and cycle.green_phase.accepted_revision is None:
                    base_binding = run_state.repository_binding.with_base_sha(cycle.red_phase.accepted_revision if cycle.red_phase else run_state.semantic_base_revision)
                    green_outcome = await self._execute_phase(
                        phase=TddPhase.GREEN,
                        work_unit=self.developer_factory.build(contract, cycle.step),
                        base_binding=base_binding,
                    )
                    if not green_outcome.accepted:
                        run_state = replace(
                            run_state,
                            current_pool="replan_ready",
                            contract=replace(contract, status="replan_ready"),
                            blocked_reason=green_outcome.blocked_reason,
                            cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, green_phase=green_outcome.phase_state, pool="replan_ready")),
                        )
                        snapshot = self._save_run_state(snapshot, run_state)
                        return self._result_from_run_state(run_state)
                    cycle = replace(
                        cycle,
                        green_phase=green_outcome.phase_state,
                        candidate_revision=green_outcome.phase_state.accepted_revision,
                        pool="review_ready",
                    )
                    run_state = replace(
                        run_state,
                        current_pool="review_ready",
                        contract=replace(contract, status="review_ready"),
                        cycles=self._replace_current_cycle(run_state.cycles, cycle),
                    )
                    snapshot = self._save_run_state(snapshot, run_state)
                    continue
                raise ValueError("cycle_active run state has no remaining executable phase")
            if run_state.current_pool == "review_ready":
                cycle = run_state.current_cycle()
                if cycle is None or cycle.candidate_revision is None:
                    raise ValueError("review_ready run state requires a candidate revision")
                review_material = self._review_material(contract, run_state, cycle)
                review = await self.reviewer.review(
                    contract=contract,
                    run_state=run_state,
                    cycle=cycle,
                    candidate_revision=cycle.candidate_revision,
                    review_material=review_material,
                )
                cycle = replace(cycle, review_result=review, review_history=[*cycle.review_history, review])
                if review.verdict == "approved":
                    completed_refs = sorted(set(run_state.completed_requirement_refs).union(cycle.step.requirement_refs))
                    cycle = replace(cycle, semantic_revision=cycle.candidate_revision, pool="approved")
                    run_state = replace(
                        run_state,
                        current_pool="approved",
                        contract=replace(contract, status="approved"),
                        semantic_base_revision=cycle.candidate_revision,
                        repository_binding=run_state.repository_binding.with_base_sha(cycle.candidate_revision),
                        completed_requirement_refs=completed_refs,
                        blocked_reason=None,
                        cycles=self._replace_current_cycle(run_state.cycles, cycle),
                    )
                    snapshot = self._save_run_state(snapshot, run_state)
                    continue
                if review.verdict == "repair_required":
                    if cycle.repair_attempts >= self.max_semantic_repairs:
                        run_state = replace(
                            run_state,
                            current_pool="replan_ready",
                            contract=replace(contract, status="replan_ready"),
                            blocked_reason="semantic repair budget exhausted",
                            cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, pool="replan_ready")),
                        )
                        snapshot = self._save_run_state(snapshot, run_state)
                        return self._result_from_run_state(run_state)
                    run_state = replace(
                        run_state,
                        current_pool="repair_ready",
                        contract=replace(contract, status="repair_ready"),
                        blocked_reason=None,
                        cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, pool="repair_ready")),
                    )
                    snapshot = self._save_run_state(snapshot, run_state)
                    continue
                run_state = replace(
                    run_state,
                    current_pool="replan_ready",
                    contract=replace(contract, status="replan_ready"),
                    blocked_reason=review.rationale,
                    cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, pool="replan_ready")),
                )
                snapshot = self._save_run_state(snapshot, run_state)
                return self._result_from_run_state(run_state)
            if run_state.current_pool == "repair_ready":
                cycle = run_state.current_cycle()
                if cycle is None or cycle.review_result is None or cycle.candidate_revision is None:
                    raise ValueError("repair_ready run state requires a review result and candidate revision")
                repair_outcome = await self._execute_phase(
                    phase=TddPhase.GREEN,
                    work_unit=self.repair_factory.build(contract, cycle, cycle.review_result),
                    base_binding=run_state.repository_binding.with_base_sha(cycle.candidate_revision),
                )
                if not repair_outcome.accepted:
                    run_state = replace(
                        run_state,
                        current_pool="replan_ready",
                        contract=replace(contract, status="replan_ready"),
                        blocked_reason=repair_outcome.blocked_reason,
                        cycles=self._replace_current_cycle(run_state.cycles, replace(cycle, pool="replan_ready", green_phase=repair_outcome.phase_state)),
                    )
                    snapshot = self._save_run_state(snapshot, run_state)
                    return self._result_from_run_state(run_state)
                cycle = replace(
                    cycle,
                    repair_attempts=cycle.repair_attempts + 1,
                    green_phase=repair_outcome.phase_state,
                    candidate_revision=repair_outcome.phase_state.accepted_revision,
                    pool="review_ready",
                )
                run_state = replace(
                    run_state,
                    current_pool="review_ready",
                    contract=replace(contract, status="review_ready"),
                    cycles=self._replace_current_cycle(run_state.cycles, cycle),
                )
                snapshot = self._save_run_state(snapshot, run_state)
                continue
            raise ValueError(f"unsupported contract run pool: {run_state.current_pool}")

    def _save_run_state(self, snapshot: TddSnapshot, run_state: BehaviorContractRunState) -> TddSnapshot:
        updated_snapshot = replace(
            snapshot,
            repository_binding=run_state.repository_binding,
            current_trusted_revision=run_state.semantic_base_revision,
            contract_runs={**snapshot.contract_runs, run_state.contract.id: run_state},
        )
        self.state_repo.save(updated_snapshot)
        return updated_snapshot

    def _replace_current_cycle(self, cycles: list[ContractCycleRecord], replacement: ContractCycleRecord) -> list[ContractCycleRecord]:
        if not cycles:
            raise ValueError("expected at least one cycle to replace")
        return [*cycles[:-1], replacement]

    def _result_from_run_state(self, run_state: BehaviorContractRunState) -> BehaviorContractCoordinationResult:
        return BehaviorContractCoordinationResult(
            contract_id=run_state.contract.id,
            current_binding=run_state.repository_binding.with_base_sha(run_state.semantic_base_revision),
            semantic_revision=run_state.semantic_base_revision,
            current_pool=run_state.current_pool,
            cycles=list(run_state.cycles),
            completed_requirement_refs=list(run_state.completed_requirement_refs),
            blocked_reason=run_state.blocked_reason,
        )

    async def _execute_phase(
        self,
        *,
        phase: TddPhase,
        work_unit: DevelopmentWorkUnit,
        base_binding: RepositoryBinding,
    ) -> _PhaseOutcome:
        recorded_at = _utc_now()
        base_sha = base_binding.base_sha
        try:
            result = await self.execution_gateway.execute(work_unit, base_binding)
        except Exception as error:
            return _PhaseOutcome(
                attempt=None,  # type: ignore[arg-type]
                phase_state=_transport_failure_state(phase, work_unit.id, base_sha, recorded_at, str(error)),
                accepted=False,
                blocked_reason=f"{phase.value} phase transport failure",
            )
        phase_state = _phase_state_from_result(phase, work_unit.id, base_sha, recorded_at, result)
        if not result.accepted:
            return _PhaseOutcome(
                attempt=None,  # type: ignore[arg-type]
                phase_state=phase_state,
                accepted=False,
                blocked_reason=_blocked_reason_for_result(phase, result),
            )
        if not result.accepted_revision:
            return _PhaseOutcome(
                attempt=None,  # type: ignore[arg-type]
                phase_state=phase_state,
                accepted=False,
                blocked_reason=f"accepted {phase.value} phase missing trusted accepted revision",
            )
        return _PhaseOutcome(attempt=None, phase_state=phase_state, accepted=True)

    def _review_material(
        self,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        cycle: ContractCycleRecord,
    ) -> str:
        if self.review_material_provider is None:
            evidence_location = None
            if cycle.green_phase is not None:
                evidence_location = cycle.green_phase.evidence_location
            return (
                f"candidate_revision={cycle.candidate_revision}\n"
                f"evidence_location={evidence_location}\n"
                f"prior_semantic_revision={run_state.semantic_base_revision}\n"
            )
        return self.review_material_provider.render(contract, run_state, cycle)


def _json_object(text: str, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return payload


def _contract_prompt(*, project_id: str, requirement_text: str) -> str:
    return f"""Produce one JSON object for ATHBA PR16.
Return only JSON.
Project id: {project_id}
Requirement:
{requirement_text}

Create a bounded provider-neutral BehaviorContract with these fields:
id, project_id, component_name, capability, requirement_source, observable_requirements,
invariants, production_paths, test_paths, public_api, error_semantics, non_goals,
completion_criteria, status.

Each observable_requirements item must contain:
ref, summary, observable_outcome, test_hint, error_expectation, preserves_state_on_failure.

Do not include worker ids, model ids, GPU ids, endpoints, ports, or backend selection."""


def _step_prompt(contract: BehaviorContract, run_state: BehaviorContractRunState) -> str:
    prior_steps = [cycle.step.to_dict() for cycle in run_state.cycles]
    return json.dumps(
        {
            "instruction": "Act as ATHBA's Tester planner. Return one JSON object only.",
            "contract": contract.to_dict(),
            "current_pool": run_state.current_pool,
            "completed_requirement_refs": run_state.completed_requirement_refs,
            "prior_steps": prior_steps,
            "required_output": {
                "status": "propose|complete",
                "rationale": "string",
                "proposal": {
                    "step_id": "string",
                    "requirement_refs": ["exactly one contract ref"],
                    "focused_behavior": "one smallest useful missing observable behavior",
                    "test_name": "pytest node id",
                    "expected_result": "exact observable result",
                    "test_path": "one allowed test path",
                    "production_path": "one allowed production path",
                    "red_objective": "Tester RED prompt material",
                    "green_objective": "Developer GREEN prompt material",
                    "reason_next_smallest": "why this is the next smallest useful step",
                    "exception_type": "optional",
                    "exception_message": "optional"
                },
                "completed_requirement_refs": ["all contract refs only when complete"]
            },
            "rules": [
                "do not repeat already covered requirements",
                "do not combine unrelated new behaviors into one proposal",
                "do not include implementation details",
                "do not leak worker, GPU, model, endpoint, or port data",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _review_prompt(
    *,
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    candidate_revision: str,
    review_material: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Act as ATHBA's Senior Reviewer. Return one JSON object only.",
            "contract": contract.to_dict(),
            "current_pool": run_state.current_pool,
            "candidate_revision": candidate_revision,
            "step": cycle.step.to_dict(),
            "prior_semantic_revision": run_state.semantic_base_revision,
            "review_material": review_material,
            "required_output": {
                "verdict": "approved|repair_required|replan_required",
                "rationale": "string",
                "findings": ["concrete findings"],
                "candidate_revision": candidate_revision,
                "step_id": cycle.step.step_id,
                "evidence_refs": ["optional evidence refs"],
                "repair_instructions": ["bounded production-only repair instructions when repair_required"],
            },
            "criteria": [
                "faithful contract behavior not test gaming",
                "simple direct readable code",
                "preserves prior approved behavior",
                "no dead imports or dead code",
                "no misleading or noisy comments",
                "no speculative abstractions or future behavior",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _tester_objective(contract: BehaviorContract, step: TddStepProposal) -> str:
    return (
        "Act in ATHBA's Tester role during RED. "
        f"Work only within {step.test_path}. Preserve accepted tests. Add exactly one focused new pytest test named {step.test_name}. "
        f"Target behavior: {step.focused_behavior}. Expected observable result: {step.expected_result}. "
        f"Requirement refs: {', '.join(step.requirement_refs)}. "
        "Do not edit production code. Do not try to make the test pass. "
        "Do not add helper functions, fixtures, comments, or docstrings unless strictly required. "
        f"Contract component: {contract.component_name}. RED objective: {step.red_objective}"
    )


def _developer_objective(contract: BehaviorContract, step: TddStepProposal) -> str:
    return (
        "Act in ATHBA's Developer role during GREEN. "
        f"Work only within {step.production_path}. Do not edit tests. The focused failing test is {step.test_name}. "
        f"Implement only enough code for this behavior: {step.focused_behavior}. Expected observable result: {step.expected_result}. "
        f"Requirement refs: {', '.join(step.requirement_refs)}. Preserve prior accepted behavior and keep the design small, direct, and readable. "
        "Do not introduce speculative abstractions, dead code, dead imports, noisy comments, or unrelated features. "
        f"Contract component: {contract.component_name}. GREEN objective: {step.green_objective}"
    )


def _repair_objective(contract: BehaviorContract, step: TddStepProposal, review: SemanticReviewResult) -> str:
    return (
        "Act in ATHBA's Developer role during GREEN repair. "
        f"Work only within {step.production_path}. Do not edit tests. Repair the candidate for step {step.step_id}. "
        f"Requirement refs: {', '.join(step.requirement_refs)}. Keep prior accepted behavior intact. "
        "Make only the bounded production changes required by the reviewer findings. "
        f"Reviewer instructions: {' | '.join(review.repair_instructions)}. "
        f"Component: {contract.component_name}."
    )


def _is_red_already_satisfied_from_phase(outcome: _PhaseOutcome) -> bool:
    if outcome.phase_state.status != "already_satisfied":
        return False
    return RED_ALREADY_SATISFIED_FRAGMENT in (outcome.phase_state.error or "")


def _transport_failure_state(phase: TddPhase, work_unit_id: str, base_sha: str | None, recorded_at: str, error: str):
    from core.development.tdd_progression import TddPhaseState

    return TddPhaseState(
        phase=phase.value,
        work_unit_id=work_unit_id,
        base_sha=base_sha,
        status="transport_error",
        error=error,
        recorded_at=recorded_at,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
