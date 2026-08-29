"""Contract-driven TDD lane for PR16 behavior-contract orchestration."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
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
    SourceRequirementClause,
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


class GitReviewMaterialProvider:
    """Read-only Git-backed review evidence for semantic review."""

    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root)

    def render(self, contract: BehaviorContract, run_state: BehaviorContractRunState, cycle: ContractCycleRecord) -> str:
        candidate_revision = cycle.candidate_revision
        prior_semantic_revision = run_state.semantic_base_revision
        if candidate_revision is None:
            raise ValueError("review material requires a candidate revision")
        if prior_semantic_revision is None:
            raise ValueError("review material requires a prior semantic revision")

        production_path = _repository_relative_path(cycle.step.production_path, label="production path")
        test_path = _repository_relative_path(cycle.step.test_path, label="test path")
        self._verify_revision(candidate_revision)
        self._verify_revision(prior_semantic_revision)

        payload = {
            "candidate_revision": candidate_revision,
            "prior_semantic_revision": prior_semantic_revision,
            "focused_tdd_step": cycle.step.to_dict(),
            "production_diff": self._git(
                "diff",
                "--unified=3",
                prior_semantic_revision,
                candidate_revision,
                "--",
                production_path,
                test_path,
            ),
            "production_source": {
                "path": production_path,
                "content": self._git("show", f"{candidate_revision}:{production_path}"),
            },
            "test_source": {
                "path": test_path,
                "content": self._git("show", f"{candidate_revision}:{test_path}"),
            },
            "rack_ai_evidence": {
                "evidence_location": cycle.green_phase.evidence_location if cycle.green_phase else None,
                "change_id": cycle.green_phase.change_id if cycle.green_phase else None,
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    def _verify_revision(self, revision: str) -> None:
        self._git("rev-parse", "--verify", f"{revision}^{{commit}}")

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"git {' '.join(args)} failed: {detail}")
        return result.stdout.strip()


class RequirementClausePlanner:
    """Turn one component requirement into machine-checkable source clauses."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def create_clauses(self, *, project_id: str, requirement_text: str) -> list[SourceRequirementClause]:
        request = ReasoningRequest(
            purpose="athba_source_requirement_clauses",
            prompt=_source_clause_prompt(project_id=project_id, requirement_text=requirement_text),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        payload = _json_object(result.text, label="source requirement clauses")
        raw_clauses = payload.get("clauses")
        if not isinstance(raw_clauses, list):
            raise ValueError("source requirement clauses response must include a clauses list")
        clauses = [SourceRequirementClause.from_dict(dict(item)) for item in raw_clauses]
        if not clauses:
            raise ValueError("source requirement clauses must not be empty")
        refs = [clause.ref for clause in clauses]
        duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
        if duplicates:
            raise ValueError(f"duplicate source clause refs are not allowed: {duplicates}")
        return clauses


class BehaviorContractPlanner:
    """Turn one component requirement into a structured provider-neutral contract."""

    def __init__(self, gateway: ReasoningGateway, clause_planner: RequirementClausePlanner | None = None):
        self.gateway = gateway
        self.clause_planner = clause_planner or RequirementClausePlanner(gateway)

    async def create_contract(
        self,
        *,
        project_id: str,
        requirement_text: str,
        production_paths: list[str] | None = None,
        test_paths: list[str] | None = None,
    ) -> BehaviorContract:
        normalized_production_paths = _normalize_allowed_paths(production_paths, label="allowed production paths")
        normalized_test_paths = _normalize_allowed_paths(test_paths, label="allowed test paths")
        source_clauses = await self.clause_planner.create_clauses(project_id=project_id, requirement_text=requirement_text)
        request = ReasoningRequest(
            purpose="athba_behavior_contract",
            prompt=_contract_prompt(
                project_id=project_id,
                requirement_text=requirement_text,
                source_clauses=source_clauses,
                production_paths=normalized_production_paths,
                test_paths=normalized_test_paths,
            ),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        return BehaviorContract.from_dict(
            _json_object(result.text, label="behavior contract"),
            allowed_production_paths=normalized_production_paths,
            allowed_test_paths=normalized_test_paths,
        )


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
        return self._validate_decision(contract, run_state, decision)

    def _validate_decision(
        self,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        decision: TddStepDecision,
    ) -> TddStepDecision:
        requirement_refs = contract.requirement_refs()
        requirement_ref_set = set(requirement_refs)
        approved_ref_set = set(run_state.completed_requirement_refs)
        claimed_ref_set = set(decision.completed_requirement_refs)
        unknown_claimed_refs = claimed_ref_set - requirement_ref_set
        if unknown_claimed_refs:
            raise ValueError("completion decisions cannot reference requirements outside the contract")
        if decision.status == "complete":
            if approved_ref_set != requirement_ref_set:
                raise ValueError("completion requires every contract requirement to be semantically approved")
            return replace(
                decision,
                completed_requirement_refs=[ref for ref in requirement_refs if ref in approved_ref_set],
            )

        assert decision.proposal is not None
        proposal = decision.proposal
        if len(proposal.requirement_refs) != 1:
            raise ValueError("each TDD step proposal must target exactly one requirement ref")
        proposal_ref = proposal.requirement_refs[0]
        if proposal_ref not in requirement_ref_set:
            raise ValueError("step proposal referenced a requirement outside the contract")
        if proposal_ref in approved_ref_set:
            raise ValueError("step proposal repeated a requirement that is already semantically covered")
        if proposal.test_path not in contract.test_paths:
            raise ValueError("step proposal test path is outside the contract")
        if proposal.production_path not in contract.production_paths:
            raise ValueError("step proposal production path is outside the contract")
        return decision


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
                commands=[["python3", "scripts/assert_test_fails.py", step.test_name, "expected failure"]],
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
                commands=[["python3", "-m", "pytest", "-q", step.test_name], ["python3", "-m", "pytest", "-q", step.test_path]],
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
                commands=[["python3", "-m", "pytest", "-q", cycle.step.test_name], ["python3", "-m", "pytest", "-q", cycle.step.test_path]],
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
        self.review_material_provider = review_material_provider or _default_review_material_provider(repository_binding)
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
                        completed_requirement_refs=_ordered_completed_requirement_refs(contract, run_state.completed_requirement_refs),
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
            raise ValueError("semantic review requires a repository review material provider or registered repository root")
        return self.review_material_provider.render(contract, run_state, cycle)


def _json_object(text: str, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return payload


def _source_clause_prompt(*, project_id: str, requirement_text: str) -> str:
    return json.dumps(
        {
            "instruction": "Produce ATHBA PR16 source requirement clauses as raw JSON only.",
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "include one top-level clauses array",
                "do not add extra fields outside the required schema",
            ],
            "project_id": project_id,
            "requirement_text": requirement_text,
            "required_json_schema": {
                "clauses": [
                    {
                        "ref": "string",
                        "text": "string",
                        "kind": "string",
                    }
                ]
            },
            "rules": [
                "one source obligation per clause",
                "do not bundle unrelated behaviors into one clause",
                "preserve happy-path, failure, query, and state-preservation obligations from the source text",
                "do not include implementation details",
                "do not invent requirements beyond reasonable decomposition of the supplied text",
                "keep the clause set complete enough that every meaningful behavioral obligation from the source text is represented",
                "do not include worker ids, model ids, GPU ids, endpoints, ports, or backend selection",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _contract_prompt(
    *,
    project_id: str,
    requirement_text: str,
    source_clauses: list[SourceRequirementClause],
    production_paths: list[str],
    test_paths: list[str],
) -> str:
    schema = {
        "id": "string",
        "project_id": "string",
        "component_name": "string",
        "capability": "string",
        "requirement_source": "string",
        "source_clauses": [
            {
                "ref": "string",
                "text": "string",
                "kind": "string",
            }
        ],
        "observable_requirements": [
            {
                "ref": "string",
                "source_refs": ["string"],
                "summary": "string",
                "observable_outcome": "string",
                "test_hint": "string",
                "error_expectation": "string or null",
                "preserves_state_on_failure": "boolean",
            }
        ],
        "invariants": ["string"],
        "production_paths": ["string"],
        "test_paths": ["string"],
        "public_api": ["string"],
        "error_semantics": ["string"],
        "non_goals": ["string"],
        "completion_criteria": ["string"],
        "status": "tdd_ready",
    }
    return json.dumps(
        {
            "instruction": "Produce one ATHBA PR16 BehaviorContract as raw JSON only.",
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "include every required field exactly once",
                "do not add extra fields",
            ],
            "project_id": project_id,
            "requirement_text": requirement_text,
            "source_clauses": [clause.to_dict() for clause in source_clauses],
            "allowed_production_paths": production_paths,
            "allowed_test_paths": test_paths,
            "path_rules": [
                "production_paths means repository-relative source file paths only",
                "test_paths means repository-relative pytest file paths only",
                "choose emitted production_paths only from allowed_production_paths",
                "choose emitted test_paths only from allowed_test_paths",
                "valid example production path: reservation_book.py",
                "valid example test path: tests/test_reservation_book.py",
                "do not emit conceptual names such as AddResource or CreateReservation in any path field",
            ],
            "required_json_schema": schema,
            "requirement_atomicity_rules": [
                "each observable_requirements entry must describe one independently verifiable behavior or invariant slice",
                "one requirement ref must be completable by one focused semantic TDD slice",
                "if two cases require distinct tests or distinct failure conditions, give them separate refs",
                "do not bundle unrelated failure modes under one requirement ref",
                "multiple observable requirements may reference the same source clause when that improves TDD granularity",
                "do not pre-author a future Tester step list",
            ],
            "traceability_rules": [
                "every supplied source clause must be covered by at least one observable requirement source_refs entry",
                "copy source clause refs exactly into source_refs",
                "do not invent source refs",
                "do not leave a source clause represented only in invariants, completion_criteria, or error_semantics",
                "each observable requirement must include a non-empty source_refs array",
            ],
            "domain_rules": [
                "status must be exactly tdd_ready",
                "public_api must be an array of strings",
                "error_semantics must be an array of strings",
                "do not include worker ids, model ids, GPU ids, endpoints, ports, or backend selection",
            ],
        },
        indent=2,
        sort_keys=True,
    )


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
                "completed_requirement_refs": ["optional consistency echo only; does not grant completion authority"]
            },
            "rules": [
                "do not repeat already covered requirements",
                "do not combine unrelated new behaviors into one proposal",
                "do not include implementation details",
                "do not leak worker, GPU, model, endpoint, or port data",
                "never declare completion unless all requirement refs are already semantically approved in persisted state",
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


def _normalize_allowed_paths(paths: list[str] | None, *, label: str) -> list[str]:
    if paths is None:
        return []
    if not isinstance(paths, list):
        raise ValueError(f"{label} must be a list")
    return [_repository_relative_path(path, label=label) for path in paths]


def _default_review_material_provider(repository_binding: RepositoryBinding) -> ReviewMaterialProvider | None:
    if repository_binding.registered_root is None:
        return None
    return GitReviewMaterialProvider(repository_binding.registered_root)


def _ordered_completed_requirement_refs(contract: BehaviorContract, completed_requirement_refs: list[str]) -> list[str]:
    completed_ref_set = set(completed_requirement_refs)
    return [ref for ref in contract.requirement_refs() if ref in completed_ref_set]


def _repository_relative_path(path: str, *, label: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"{label} must be non-empty")
    normalized = path.replace("\\", "/")
    candidate = PurePosixPath(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} must be repository-relative")
    return candidate.as_posix()


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
