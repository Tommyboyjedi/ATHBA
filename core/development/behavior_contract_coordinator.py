"""Contract-driven TDD lane for PR16 behavior-contract orchestration."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, cast

from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.contract_run_store import ContractRunStore
from core.development.failure_progression import (
    DependencyDecision,
    DependencyDisposition,
    FailureClassification,
    FailureDecision,
    FailureObservation,
    FailureProgressState,
    FailureProgressionPolicy,
    ProgressionAction,
    RetryBudget,
    RetryRoute,
)
from core.development.failure_state import TERMINAL_CONTRACT_POOLS
from core.development import failure_routing
from core.development.resource_split import (
    MAX_SPLIT_DEPTH,
    ResourceLimitSplitPlanner,
    ResourceSplitPlannerRequest,
    SplitDecisionStatus,
    approval_resolution,
    next_ready_split_child,
    split_aware_success_state,
    split_depth_for_step,
    split_record,
    step_proposal,
    trusted_revision_for_child,
)
from core.development.tdd_cycle_coordination import TddStateRepository
from core.development.tdd_phase_execution import (
    PhaseExecutionRequest,
    PhaseOutcome,
    TddPhaseExecutor as PhaseExecutor,
    RED_ALREADY_SATISFIED_FRAGMENT,
    is_red_already_satisfied,
)
from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractLoadOptions,
    BehaviorContractRequirement,
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
from core.development.specification_gatekeeper import (
    GatekeeperAssessmentRequest,
    GatekeeperStateRequest,
    SpecificationGapTddAdapter,
    SpecificationGatekeeper,
)
from core.development.policy_scope_violation import (
    PolicyScopeDisposition,
    PolicyScopeResolutionRequest,
    PolicyScopeViolationResolver,
)
from core.development.python_test_runtime import PythonPytestRuntime
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


@dataclass(frozen=True)
class RepositoryMaterialRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState
    revision: str | None = None


@dataclass(frozen=True)
class ReviewMaterialRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState
    cycle: ContractCycleRecord


@dataclass(frozen=True)
class ContractPlanningRequest:
    project_id: str
    requirement_text: str
    production_paths: list[str] | None = None
    test_paths: list[str] | None = None


@dataclass(frozen=True)
class StepDecisionRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState


@dataclass(frozen=True)
class StepDecisionValidationRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState
    decision: TddStepDecision


@dataclass(frozen=True)
class DependencyDecisionRequest:
    contract: BehaviorContract
    step: TddStepProposal
    evidence: FailureObservation
    trusted_revision: str | None


@dataclass(frozen=True)
class SemanticReviewRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState
    cycle: ContractCycleRecord
    candidate_revision: str
    review_material: str


@dataclass(frozen=True)
class WorkUnitBuildRequest:
    contract: BehaviorContract
    step: TddStepProposal
    repository_material: dict[str, object] | None = None


@dataclass(frozen=True)
class RepairWorkUnitBuildRequest:
    contract: BehaviorContract
    cycle: ContractCycleRecord
    review: SemanticReviewResult


class ReviewMaterialProvider(Protocol):
    def render(self, request: ReviewMaterialRequest) -> str:
        ...


class TesterRepositoryMaterialProvider(Protocol):
    """Supply bounded, revision-pinned repository facts for TDD planning."""

    def render(self, request: RepositoryMaterialRequest) -> dict[str, object]:
        ...


class EnvironmentRecovery(Protocol):
    """ATHBA-owned environment repair followed by a mandatory health proof."""

    async def recover_and_verify(self, project_id: str) -> bool:
        ...


class GitReviewMaterialProvider:
    """Read-only Git-backed review evidence for semantic review."""

    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root)

    def render(self, request: ReviewMaterialRequest) -> str:
        candidate_revision = request.cycle.candidate_revision
        prior_semantic_revision = request.run_state.semantic_base_revision
        if candidate_revision is None:
            raise ValueError("review material requires a candidate revision")
        if prior_semantic_revision is None:
            raise ValueError("review material requires a prior semantic revision")

        production_path = _repository_relative_path(request.cycle.step.production_path, label="production path")
        test_path = _repository_relative_path(request.cycle.step.test_path, label="test path")
        self._verify_revision(candidate_revision)
        self._verify_revision(prior_semantic_revision)

        payload = {
            "candidate_revision": candidate_revision,
            "prior_semantic_revision": prior_semantic_revision,
            "focused_tdd_step": request.cycle.step.to_dict(),
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
                "evidence_location": request.cycle.green_phase.evidence_location if request.cycle.green_phase else None,
                "change_id": request.cycle.green_phase.change_id if request.cycle.green_phase else None,
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


class GitTesterRepositoryMaterialProvider:
    """Read only the contract-relevant files from the target repository."""

    _MAX_FILE_CHARS = 16_000

    def __init__(self, repository_root: str | Path):
        self.repository_root = Path(repository_root)

    def render(self, request: RepositoryMaterialRequest) -> dict[str, object]:
        selected_revision = request.revision or request.run_state.semantic_base_revision or request.run_state.repository_binding.base_sha
        if selected_revision is None:
            raise ValueError("repository context requires a trusted revision")
        self._verify_revision(selected_revision)
        files = self._git("ls-tree", "-r", "--name-only", selected_revision).splitlines()
        production_files = [self._file_material(selected_revision, path) for path in request.contract.production_paths]
        test_files = [self._file_material(selected_revision, path) for path in request.contract.test_paths]
        return {
            "repository_kind": "external_registered_repository",
            "trusted_revision": selected_revision,
            "files": files[:200],
            "production_files": production_files,
            "test_files": test_files,
            "known_pytest_nodes": [node for material in test_files for node in cast(list[str], material["pytest_nodes"])],
            "all_contract_files_empty": all(
                not str(material["content"]).strip() for material in [*production_files, *test_files]
            ),
        }

    def _file_material(self, revision: str, path: str) -> dict[str, object]:
        normalized_path = _repository_relative_path(path, label="repository context path")
        content = self._optional_git_show(revision, normalized_path)
        return {
            "path": normalized_path,
            "module_name": _python_module_name(normalized_path),
            "content": content[: self._MAX_FILE_CHARS],
            "truncated": len(content) > self._MAX_FILE_CHARS,
            "pytest_nodes": _pytest_nodes(normalized_path, content),
        }

    def _optional_git_show(self, revision: str, path: str) -> str:
        result = subprocess.run(
            ["git", "show", f"{revision}:{path}"],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        if f"path '{path}' does not exist" in (result.stderr or result.stdout):
            return ""
        detail = (result.stderr or result.stdout).strip()
        raise ValueError(f"git show {revision}:{path} failed: {detail}")

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
        return result.stdout


class RequirementClausePlanner:
    """Turn one component requirement into machine-checkable source clauses."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def create_clauses(self, *, project_id: str, requirement_text: str) -> list[SourceRequirementClause]:
        reasoning_request = ReasoningRequest(
            purpose="athba_source_requirement_clauses",
            prompt=_source_clause_prompt(project_id=project_id, requirement_text=requirement_text),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(reasoning_request)
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

    async def create_contract(self, request: ContractPlanningRequest | None = None, **legacy) -> BehaviorContract:
        request = request or ContractPlanningRequest(
            legacy["project_id"],
            legacy["requirement_text"],
            legacy.get("production_paths"),
            legacy.get("test_paths"),
        )
        normalized_production_paths = _normalize_allowed_paths(request.production_paths, label="allowed production paths")
        normalized_test_paths = _normalize_allowed_paths(request.test_paths, label="allowed test paths")
        source_clauses = await self.clause_planner.create_clauses(
            project_id=request.project_id,
            requirement_text=request.requirement_text,
        )
        reasoning_request = ReasoningRequest(
            purpose="athba_behavior_contract",
            prompt=_contract_prompt(
                project_id=request.project_id,
                requirement_text=request.requirement_text,
                source_clauses=source_clauses,
                production_paths=normalized_production_paths,
                test_paths=normalized_test_paths,
            ),
            project_id=request.project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(reasoning_request)
        try:
            return _contract_from_response(
                result.text,
                label="behavior contract",
                allowed_production_paths=normalized_production_paths,
                allowed_test_paths=normalized_test_paths,
            )
        except ValueError as error:
            if not _is_recoverable_contract_error(error):
                raise
            repair_request = ReasoningRequest(
                purpose="athba_behavior_contract_repair",
                prompt=_contract_repair_prompt(
                    project_id=request.project_id,
                    requirement_text=request.requirement_text,
                    source_clauses=source_clauses,
                    production_paths=normalized_production_paths,
                    test_paths=normalized_test_paths,
                    invalid_contract_text=result.text,
                    validation_error=str(error),
                ),
                project_id=request.project_id,
                requires_large_context=False,
            )
            repair_result = await self.gateway.reason(repair_request)
            return _contract_from_response(
                repair_result.text,
                label="behavior contract repair",
                allowed_production_paths=normalized_production_paths,
                allowed_test_paths=normalized_test_paths,
            )


class DynamicTddPlanner:
    """Use reasoning to choose the next smallest useful RED step within a contract."""

    def __init__(
        self,
        gateway: ReasoningGateway,
        repository_material_provider: TesterRepositoryMaterialProvider | None = None,
    ):
        self.gateway = gateway
        self.repository_material_provider = repository_material_provider

    async def decide_next_step(
        self,
        request: StepDecisionRequest | BehaviorContract,
        run_state: BehaviorContractRunState | None = None,
    ) -> TddStepDecision:
        request = request if isinstance(request, StepDecisionRequest) else StepDecisionRequest(request, _require_run_state(run_state))
        repository_material = _repository_material_for_run_state(
            request.contract,
            request.run_state,
            provider=self.repository_material_provider,
        )
        context = request
        reasoning_request = ReasoningRequest(
            purpose="athba_tdd_step_selection",
            prompt=_step_prompt(contract=context.contract, run_state=context.run_state, repository_material=repository_material),
            project_id=context.contract.project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(reasoning_request)
        try:
            return _decision_from_response(context.contract, context.run_state, result.text, label="step decision")
        except ValueError as error:
            if not _is_recoverable_step_error(error):
                raise
            repair_request = ReasoningRequest(
                purpose="athba_tdd_step_selection_repair",
                prompt=_step_repair_prompt(
                    contract=context.contract,
                    run_state=context.run_state,
                    invalid_step_text=result.text,
                    validation_error=str(error),
                    repository_material=repository_material,
                ),
                project_id=context.contract.project_id,
                requires_large_context=False,
            )
            repair_result = await self.gateway.reason(repair_request)
            return _decision_from_response(context.contract, context.run_state, repair_result.text, label="step decision repair")

    def _validate_decision(self, request: StepDecisionValidationRequest) -> TddStepDecision:
        contract = request.contract
        run_state = request.run_state
        decision = request.decision
        requirement_refs = run_state.active_requirement_refs()
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
        ready_refs = set(contract.ready_requirement_refs(run_state.completed_requirement_refs))
        if proposal_ref not in ready_refs:
            raise ValueError("step proposal selected a requirement whose prerequisites are not semantically approved")
        if proposal.test_path not in contract.test_paths:
            raise ValueError("step proposal test path is outside the contract")
        if proposal.production_path not in contract.production_paths:
            raise ValueError("step proposal production path is outside the contract")
        if not _is_valid_pytest_node_for_path(proposal.test_name, proposal.test_path):
            raise ValueError("step proposal test name must be a pytest node id within the selected test path")
        if run_state.repository_binding.registered_root is not None and _has_athba_internal_leakage(proposal):
            raise ValueError("step proposal leaked ATHBA-internal module or path assumptions into an external repository")
        return decision


class DependencyPrerequisitePlanner:
    """Small Behavior-Planner authority for mechanical dependency evidence."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def decide(self, request: DependencyDecisionRequest | None = None, **legacy) -> DependencyDecision:
        request = request or DependencyDecisionRequest(
            legacy["contract"],
            legacy["step"],
            legacy["evidence"],
            legacy.get("trusted_revision"),
        )
        reasoning_request = ReasoningRequest(
            purpose="athba_dependency_prerequisite_decision",
            project_id=request.contract.project_id,
            requires_large_context=False,
            prompt=json.dumps({
                "instruction": "Choose exactly one bounded dependency decision as raw JSON. For add_prerequisite, prerequisite_observable must state one externally observable capability, not an implementation, API invocation, test, or patch instruction. Do not redesign.",
                "blocked_requirement_ref": request.step.requirement_refs[0],
                "planned_requirements": [item.to_dict() for item in request.contract.observable_requirements],
                "trusted_revision": request.trusted_revision,
                "mechanical_failure": request.evidence.to_dict(),
                "schema": {"disposition": "already_planned|add_prerequisite|reject_dependency", "parent_requirement_ref": "string", "prerequisite_refs": ["string"], "prerequisite_observable": "string|null", "rationale": "string"},
            }, sort_keys=True),
        )
        result = await self.gateway.reason(reasoning_request)
        decision = DependencyDecision.from_dict(_json_object(result.text, label="dependency decision"))
        if decision.parent_requirement_ref != request.step.requirement_refs[0]:
            raise ValueError("dependency decision must retain the blocked requirement")
        if decision.disposition is DependencyDisposition.ALREADY_PLANNED:
            known = set(request.contract.requirement_refs())
            if not set(decision.prerequisite_refs).issubset(known):
                raise ValueError("existing planned dependency must reference contract requirements")
        if decision.disposition is DependencyDisposition.ADD_PREREQUISITE and len(decision.prerequisite_refs) != 1:
            raise ValueError("a justified prerequisite decision must add one smallest prerequisite")
        return decision


class SeniorReviewer:
    """Semantic gate that is separate from Rack AI mechanical acceptance."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def review(self, request: SemanticReviewRequest | None = None, **legacy) -> SemanticReviewResult:
        request = request or SemanticReviewRequest(
            legacy["contract"],
            legacy["run_state"],
            legacy["cycle"],
            legacy["candidate_revision"],
            legacy["review_material"],
        )
        reasoning_request = ReasoningRequest(
            purpose="athba_senior_review",
            prompt=_review_prompt(
                contract=request.contract,
                run_state=request.run_state,
                cycle=request.cycle,
                candidate_revision=request.candidate_revision,
                review_material=request.review_material,
            ),
            project_id=request.contract.project_id,
            requires_large_context=True,
        )
        result = await self.gateway.reason(reasoning_request)
        review = SemanticReviewResult.from_dict(_json_object(result.text, label="semantic review"))
        if review.candidate_revision != request.candidate_revision:
            raise ValueError("semantic review candidate revision mismatch")
        if review.step_id != request.cycle.step.step_id:
            raise ValueError("semantic review step id mismatch")
        return review


class ContractTesterWorkUnitFactory:
    def __init__(self, runtime: PythonPytestRuntime | None = None):
        self.runtime = runtime or PythonPytestRuntime()

    def build(self, request: WorkUnitBuildRequest) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=red_work_unit_id(request.step.step_id),
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=_tester_objective(request.contract, request.step, request.repository_material),
            allowed_paths=[request.step.test_path],
            acceptance=AcceptanceContract(
                commands=[self.runtime.red_command(request.step.test_name)],
                required_artifacts=[request.step.test_path],
            ),
            status=WorkUnitStatus.READY,
        )


class ContractDeveloperWorkUnitFactory:
    def __init__(self, runtime: PythonPytestRuntime | None = None):
        self.runtime = runtime or PythonPytestRuntime()

    def build(self, request: WorkUnitBuildRequest) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=green_work_unit_id(request.step.step_id),
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=_developer_objective(request.contract, request.step, request.repository_material),
            allowed_paths=[request.step.production_path],
            acceptance=AcceptanceContract(
                commands=[self.runtime.pytest_command(request.step.test_name), self.runtime.pytest_command(request.step.test_path)],
                required_artifacts=[request.step.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class ContractRepairWorkUnitFactory:
    def __init__(self, runtime: PythonPytestRuntime | None = None):
        self.runtime = runtime or PythonPytestRuntime()

    def build(self, request: RepairWorkUnitBuildRequest) -> DevelopmentWorkUnit:
        attempt_number = request.cycle.repair_attempts + 1
        return DevelopmentWorkUnit(
            id=repair_work_unit_id(request.cycle.step.step_id, attempt_number),
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=_repair_objective(request.contract, request.cycle.step, request.review),
            allowed_paths=[request.cycle.step.production_path],
            acceptance=AcceptanceContract(
                commands=[self.runtime.pytest_command(request.cycle.step.test_name), self.runtime.pytest_command(request.cycle.step.test_path)],
                required_artifacts=[request.cycle.step.production_path],
            ),
            status=WorkUnitStatus.READY,
        )



@dataclass(frozen=True)
class CoordinatorDependencies:
    execution_gateway: WorkUnitExecutionGateway
    reasoning_gateway: ReasoningGateway
    repository_binding: RepositoryBinding
    state_repo: TddStateRepository | None = None
    step_planner: DynamicTddPlanner | None = None
    reviewer: SeniorReviewer | None = None
    tester_factory: ContractTesterWorkUnitFactory | None = None
    developer_factory: ContractDeveloperWorkUnitFactory | None = None
    repair_factory: ContractRepairWorkUnitFactory | None = None
    review_material_provider: ReviewMaterialProvider | None = None
    repository_material_provider: TesterRepositoryMaterialProvider | None = None
    split_planner: ResourceLimitSplitPlanner | None = None
    max_semantic_repairs: int = 2
    gatekeeper: SpecificationGatekeeper | None = None
    gap_adapter: SpecificationGapTddAdapter | None = None
    failure_policy: FailureProgressionPolicy | None = None
    max_tester_repairs: int = 2
    max_developer_repairs: int = 2
    environment_recovery: EnvironmentRecovery | None = None
    dependency_planner: DependencyPrerequisitePlanner | None = None
    policy_scope_resolver: PolicyScopeViolationResolver | None = None


@dataclass(frozen=True)
class RunAdvance:
    run_state: BehaviorContractRunState
    return_now: bool = False


@dataclass(frozen=True)
class FailureRoutingRequest:
    run_state: BehaviorContractRunState
    phase: TddPhase
    work_unit: DevelopmentWorkUnit
    outcome: PhaseOutcome


@dataclass(frozen=True)
class FailureRouterDependencies:
    failure_policy: FailureProgressionPolicy
    environment_recovery: EnvironmentRecovery | None
    dependency_planner: DependencyPrerequisitePlanner
    split_planner: ResourceLimitSplitPlanner
    repository_material_provider: TesterRepositoryMaterialProvider | None
    max_tester_repairs: int
    max_developer_repairs: int
    policy_scope_resolver: PolicyScopeViolationResolver


async def _candidate_failure_transition(
    dependencies: FailureRouterDependencies,
    request: FailureRoutingRequest,
) -> failure_routing.FailureTransition:
    cycle = request.run_state.current_cycle()
    if cycle is None:
        raise ValueError("failed candidate routing requires an active cycle")
    observation = failure_routing.candidate_failure_observation(request.phase, request.work_unit, request.outcome)
    decision = dependencies.failure_policy.decide([observation])
    if decision.action is ProgressionAction.BLOCK_EXECUTOR:
        return failure_routing.transition_for_executor_block(decision, observation.message)
    if decision.action is ProgressionAction.RECOVER_ENVIRONMENT:
        recovered = await _environment_recovery_succeeded(dependencies, request.run_state, request.run_state.contract.project_id)
        return failure_routing.transition_for_environment(decision, observation.message, recovered)
    if decision.action is ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY:
        return await _mechanical_dependency_transition(dependencies, request, observation, decision, cycle)
    if decision.action is ProgressionAction.REPAIR_CANDIDATE:
        resolution = dependencies.policy_scope_resolver.resolve(
            PolicyScopeResolutionRequest(
                classification=decision.dominant,
                contract=request.run_state.contract,
                phase=request.phase,
                step=cycle.step,
                work_unit=request.work_unit,
                observation=observation,
            )
        )
        if resolution.disposition is not PolicyScopeDisposition.ROLE_CANDIDATE_DEFECT:
            return failure_routing.transition_for_replan(decision, resolution.blocker or observation.message)
        return _candidate_repair_transition(dependencies, request, observation, decision, cycle)
    if decision.action in {
        ProgressionAction.REPAIR_TESTER,
        ProgressionAction.REPAIR_DEVELOPER,
        ProgressionAction.REPAIR_REGRESSION,
    }:
        return _candidate_repair_transition(dependencies, request, observation, decision, cycle)
    if decision.action is ProgressionAction.SPLIT_PACKET:
        return await _split_transition(dependencies, request, observation, decision, cycle)
    if decision.action is ProgressionAction.REPLAN_DEPENDENCY:
        return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: {observation.message}")
    if decision.action is ProgressionAction.BLOCK_AMBIGUITY:
        return failure_routing.transition_for_block(decision, failure_routing.FailureRouteState.BLOCKED_AMBIGUITY, failure_routing.ContractPoolStatus.BLOCKED_AMBIGUITY, observation.message)
    if decision.action is ProgressionAction.REPLAN_INTEGRATION:
        return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: {observation.message}")
    if decision.action is ProgressionAction.REPAIR_REVIEW:
        return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: review repair is not an executable candidate route")
    if decision.action is ProgressionAction.BLOCK_ARCHITECTURE:
        return failure_routing.transition_for_block(decision, failure_routing.FailureRouteState.BLOCKED_ARCHITECTURE, failure_routing.ContractPoolStatus.BLOCKED_ARCHITECTURE, observation.message)
    if decision.action is ProgressionAction.ANALYZE_UNCLASSIFIED:
        return failure_routing.transition_for_block(decision, failure_routing.FailureRouteState.BLOCKED_UNCLASSIFIED, failure_routing.ContractPoolStatus.BLOCKED_UNCLASSIFIED, observation.message)
    return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: accepted RED is represented by successful RED execution, not failure routing")


def _candidate_repair_transition(
    dependencies: FailureRouterDependencies,
    request: FailureRoutingRequest,
    observation: FailureObservation,
    decision: FailureDecision,
    cycle: ContractCycleRecord,
) -> failure_routing.FailureTransition:
    route = _retry_route_for_action(decision.action, request.phase)
    budget = dependencies.max_tester_repairs if route is RetryRoute.TESTER_REPAIR else dependencies.max_developer_repairs
    retry_allowed = dependencies.failure_policy.retry_allowed(
        RetryBudget(state=request.run_state.failure_progress, route=route, budget=budget)
    )
    return failure_routing.transition_for_candidate_repair(
        decision,
        request.phase,
        request.work_unit,
        _trusted_revision_for_phase(request.run_state, cycle, request.phase),
        observation,
        retry_allowed,
    )


async def _mechanical_dependency_transition(
    dependencies: FailureRouterDependencies,
    request: FailureRoutingRequest,
    observation: FailureObservation,
    decision: FailureDecision,
    cycle: ContractCycleRecord,
) -> failure_routing.FailureTransition:
    planner_decision = await dependencies.dependency_planner.decide(
        DependencyDecisionRequest(request.run_state.contract, cycle.step, observation, request.run_state.semantic_base_revision)
    )
    if planner_decision.disposition is DependencyDisposition.REJECT_DEPENDENCY:
        return _candidate_repair_transition(dependencies, request, observation, decision, cycle)
    updated_contract = request.run_state.contract
    if planner_decision.disposition is DependencyDisposition.ADD_PREREQUISITE:
        updated_contract = _add_synthesized_prerequisite(request.run_state.contract, planner_decision, request.run_state)
    blocker = f"{decision.dominant.value}: deferred until {', '.join(planner_decision.prerequisite_refs)} is approved"
    return failure_routing.transition_for_dependency_deferral(decision, blocker, updated_contract, planner_decision)


def _advance_nonapproved_review(
    run_state: BehaviorContractRunState,
    contract: BehaviorContract,
    cycle: ContractCycleRecord,
    review: SemanticReviewResult,
    max_semantic_repairs: int,
) -> RunAdvance:
    if review.verdict == "repair_required":
        return _review_repair_advance(run_state, contract, cycle, max_semantic_repairs)
    if review.verdict == "replan_required":
        return _review_replan_advance(run_state, contract, cycle, review.rationale)
    raise ValueError(f"unsupported review verdict: {review.verdict}")


def _review_repair_advance(
    run_state: BehaviorContractRunState,
    contract: BehaviorContract,
    cycle: ContractCycleRecord,
    max_semantic_repairs: int,
) -> RunAdvance:
    if cycle.repair_attempts >= max_semantic_repairs:
        return _review_replan_advance(run_state, contract, cycle, "semantic repair budget exhausted")
    return RunAdvance(
        replace(
            run_state,
            current_pool="repair_ready",
            contract=replace(contract, status="repair_ready"),
            blocked_reason=None,
            cycles=_replace_current_cycle(run_state.cycles, replace(cycle, pool="repair_ready")),
        )
    )


def _review_replan_advance(
    run_state: BehaviorContractRunState,
    contract: BehaviorContract,
    cycle: ContractCycleRecord,
    rationale: str,
) -> RunAdvance:
    return RunAdvance(
        replace(
            run_state,
            current_pool="replan_ready",
            contract=replace(contract, status="replan_ready"),
            blocked_reason=rationale,
            cycles=_replace_current_cycle(run_state.cycles, replace(cycle, pool="replan_ready")),
        ),
        return_now=True,
    )


def _retry_route_for_action(action: ProgressionAction, phase: TddPhase) -> RetryRoute:
    if action is ProgressionAction.REPAIR_TESTER:
        return RetryRoute.TESTER_REPAIR
    if action is ProgressionAction.REPAIR_DEVELOPER:
        return RetryRoute.DEVELOPER_REPAIR
    return RetryRoute.TESTER_REPAIR if phase is TddPhase.RED else RetryRoute.DEVELOPER_REPAIR


async def _split_transition(
    dependencies: FailureRouterDependencies,
    request: FailureRoutingRequest,
    observation: FailureObservation,
    decision: FailureDecision,
    cycle: ContractCycleRecord,
) -> failure_routing.FailureTransition:
    requirement = _split_requirement(request.run_state.contract, cycle.step)
    split_depth = split_depth_for_step(request.run_state.failure_progress, cycle.step.step_id)
    if split_depth > MAX_SPLIT_DEPTH:
        return failure_routing.transition_for_split_replan(
            decision,
            f"{decision.dominant.value}: split depth exhausted for {cycle.step.step_id}",
        )
    trusted_revision = _trusted_revision_for_phase(request.run_state, cycle, request.phase)
    split_request = ResourceSplitPlannerRequest(
        contract=request.run_state.contract,
        requirement=requirement,
        step=cycle.step,
        evidence=observation,
        trusted_revision=trusted_revision,
        split_depth=split_depth,
        repository_material=_repository_material(
            request.run_state.contract,
            request.run_state,
            dependencies.repository_material_provider,
            trusted_revision,
        ),
    )
    try:
        resolution = await dependencies.split_planner.decide(split_request)
    except ValueError as error:
        return failure_routing.transition_for_split_replan(
            decision,
            f"{decision.dominant.value}: {error}",
        )
    if resolution.status is SplitDecisionStatus.CANNOT_SPLIT:
        return failure_routing.transition_for_split_replan(
            decision,
            f"{decision.dominant.value}: {resolution.rationale}",
        )
    split = split_record(split_request, resolution, request.work_unit.id)
    blocker = f"{decision.dominant.value}: split into {', '.join(split.child_step_ids)}"
    return failure_routing.transition_for_split_children(decision, blocker, split)


def _trusted_revision_for_phase(
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    phase: TddPhase,
) -> str | None:
    if phase is TddPhase.RED:
        return run_state.semantic_base_revision
    return cycle.red_phase.accepted_revision if cycle.red_phase else run_state.semantic_base_revision


@dataclass(frozen=True)
class ReadyPoolDependencies:
    step_planner: DynamicTddPlanner
    gatekeeper: SpecificationGatekeeper | None
    gap_adapter: SpecificationGapTddAdapter | None
    repository_binding: RepositoryBinding


@dataclass(frozen=True)
class CycleProgressionDependencies:
    tester_factory: ContractTesterWorkUnitFactory
    developer_factory: ContractDeveloperWorkUnitFactory
    repository_material_provider: TesterRepositoryMaterialProvider | None
    phase_executor: 'PhaseExecutor'
    failure_router: 'FailedCandidateRouter'


@dataclass(frozen=True)
class ReviewProgressionDependencies:
    reviewer: SeniorReviewer
    review_material_provider: ReviewMaterialProvider | None
    gatekeeper: SpecificationGatekeeper | None
    max_semantic_repairs: int


@dataclass(frozen=True)
class RepairProgressionDependencies:
    repair_factory: ContractRepairWorkUnitFactory
    phase_executor: 'PhaseExecutor'


@dataclass(frozen=True)
class FailedCandidateRouter:
    dependencies: FailureRouterDependencies

    async def route(self, request: FailureRoutingRequest) -> RunAdvance:
        transition = await _candidate_failure_transition(self.dependencies, request)
        routed = failure_routing.apply_candidate_failure_transition(
            failure_routing.CandidateFailureTransitionRequest(
                run_state=request.run_state,
                phase=request.phase,
                phase_state=request.outcome.phase_state,
            ),
            transition,
            self.dependencies.failure_policy,
        )
        return RunAdvance(routed, return_now=transition.return_now)


@dataclass(frozen=True)
class ReadyPoolProgressor:
    dependencies: ReadyPoolDependencies

    async def advance(self, run_state: BehaviorContractRunState) -> RunAdvance:
        contract = run_state.contract
        split_child = next_ready_split_child(run_state)
        if split_child is not None:
            cycle = ContractCycleRecord.from_step(
                step_proposal(split_child),
                base_revision=trusted_revision_for_child(
                    run_state.failure_progress,
                    split_child.step_id,
                )
                or run_state.semantic_base_revision,
            )
            return RunAdvance(
                replace(
                    run_state,
                    current_pool="cycle_active",
                    contract=replace(contract, status="cycle_active"),
                    cycles=[*run_state.cycles, cycle],
                    blocked_reason=None,
                )
            )
        if run_state.current_pool == "tdd_ready" and run_state.targeted_requirement_ref is None and self.dependencies.gatekeeper is not None and self.dependencies.gap_adapter is not None:
            gatekeeper_state = await self.dependencies.gatekeeper.ensure_state(
                GatekeeperStateRequest(contract, run_state.gatekeeper_state)
            )
            gatekeeper_state = await self.dependencies.gatekeeper.assess(
                GatekeeperAssessmentRequest(contract, run_state, gatekeeper_state)
            )
            gap = _first_executable_gap(contract, gatekeeper_state)
            if gap is not None:
                updated_contract = self.dependencies.gap_adapter.extend_contract_for_gap(contract, gap)
                targeted_requirement = _targeted_requirement_for_gap(updated_contract, gap)
                return RunAdvance(
                    replace(
                        run_state,
                        contract=updated_contract,
                        gatekeeper_state=gatekeeper_state,
                        targeted_requirement_ref=targeted_requirement.ref,
                        targeted_checklist_ref=gap.checklist_ref,
                        blocked_reason="targeted specification gap selected",
                    )
                )
            if _has_untraceable_executable_gap(gatekeeper_state):
                return RunAdvance(
                    replace(
                        run_state,
                        current_pool="replan_ready",
                        contract=replace(contract, status="replan_ready"),
                        gatekeeper_state=gatekeeper_state,
                        blocked_reason="specification checklist has no traceable executable gap",
                    ),
                    return_now=True,
                )
        decision = await self.dependencies.step_planner.decide_next_step(StepDecisionRequest(contract, run_state))
        if decision.status != "complete":
            assert decision.proposal is not None
            cycle = ContractCycleRecord.from_step(decision.proposal, base_revision=run_state.semantic_base_revision)
            return RunAdvance(
                replace(
                    run_state,
                    current_pool="cycle_active",
                    contract=replace(contract, status="cycle_active"),
                    cycles=[*run_state.cycles, cycle],
                )
            )
        if self.dependencies.gatekeeper is None:
            return RunAdvance(_completed_run_state(run_state), return_now=True)
        gatekeeper_state = await self.dependencies.gatekeeper.ensure_state(
                GatekeeperStateRequest(contract, run_state.gatekeeper_state)
            )
        gatekeeper_state = await self.dependencies.gatekeeper.assess(
                GatekeeperAssessmentRequest(contract, run_state, gatekeeper_state)
            )
        if gatekeeper_state.is_complete():
            completed = _completed_run_state(run_state)
            return RunAdvance(replace(completed, gatekeeper_state=gatekeeper_state), return_now=True)
        latest_assessment = gatekeeper_state.latest_assessment
        if self.dependencies.gap_adapter is not None and latest_assessment is not None and latest_assessment.gaps:
            updated_contract = self.dependencies.gap_adapter.extend_contract_for_gap(contract, latest_assessment.gaps[0])
            return RunAdvance(
                replace(
                    run_state,
                    current_pool="tdd_ready",
                    contract=replace(updated_contract, status="tdd_ready"),
                    blocked_reason="specification checklist incomplete",
                    gatekeeper_state=gatekeeper_state,
                )
            )
        return RunAdvance(
            replace(
                run_state,
                current_pool="approved",
                contract=replace(contract, status="approved"),
                blocked_reason="specification checklist incomplete",
                gatekeeper_state=gatekeeper_state,
            ),
            return_now=True,
        )


async def _advance_cycle_active(
    run_state: BehaviorContractRunState,
    dependencies: CycleProgressionDependencies,
) -> RunAdvance:
    contract = run_state.contract
    cycle = run_state.current_cycle()
    if cycle is None:
        raise ValueError("cycle_active run state requires an active cycle")
    if cycle.red_phase is not None and cycle.red_phase.accepted_revision is None:
        material = _repository_material(contract, run_state, dependencies.repository_material_provider)
        work_unit = dependencies.tester_factory.build(WorkUnitBuildRequest(contract, cycle.step, material))
        outcome = await dependencies.phase_executor.execute(
            PhaseExecutionRequest(
                TddPhase.RED,
                work_unit,
                run_state.repository_binding.with_base_sha(
                    cycle.base_revision or run_state.semantic_base_revision
                ),
            )
        )
        return await _advance_red_phase(run_state, cycle, contract, dependencies.failure_router, work_unit, outcome)
    return await _advance_green_phase(run_state, cycle, contract, dependencies)


async def _advance_red_phase(
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    contract: BehaviorContract,
    failure_router: FailedCandidateRouter,
    work_unit: DevelopmentWorkUnit,
    outcome: PhaseOutcome,
) -> RunAdvance:
    if not outcome.accepted:
        if _is_red_already_satisfied_from_phase(outcome):
            return RunAdvance(
                replace(
                    run_state,
                    current_pool="tdd_ready",
                    contract=replace(contract, status="tdd_ready"),
                    blocked_reason="step already satisfied before RED",
                    cycles=_replace_current_cycle(run_state.cycles, replace(cycle, red_phase=outcome.phase_state, pool="approved")),
                )
            )
        return await failure_router.route(FailureRoutingRequest(run_state, TddPhase.RED, work_unit, outcome))
    return RunAdvance(
        replace(
            run_state,
            cycles=_replace_current_cycle(run_state.cycles, replace(cycle, red_phase=outcome.phase_state)),
            failure_progress=split_aware_success_state(run_state.failure_progress),
            blocked_reason=None,
        )
    )


async def _advance_green_phase(
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    contract: BehaviorContract,
    dependencies: CycleProgressionDependencies,
) -> RunAdvance:
    if cycle.green_phase is None or cycle.green_phase.accepted_revision is not None:
        raise ValueError("cycle_active run state has no remaining executable phase")
    base_revision = cycle.red_phase.accepted_revision if cycle.red_phase else run_state.semantic_base_revision
    material = _repository_material(contract, run_state, dependencies.repository_material_provider, base_revision)
    work_unit = dependencies.developer_factory.build(WorkUnitBuildRequest(contract, cycle.step, material))
    outcome = await dependencies.phase_executor.execute(
        PhaseExecutionRequest(TddPhase.GREEN, work_unit, run_state.repository_binding.with_base_sha(base_revision))
    )
    if not outcome.accepted:
        return await dependencies.failure_router.route(FailureRoutingRequest(run_state, TddPhase.GREEN, work_unit, outcome))
    updated_cycle = replace(cycle, green_phase=outcome.phase_state, candidate_revision=outcome.phase_state.accepted_revision, pool="review_ready")
    return RunAdvance(
        replace(
            run_state,
            current_pool="review_ready",
            contract=replace(contract, status="review_ready"),
            cycles=_replace_current_cycle(run_state.cycles, updated_cycle),
            failure_progress=split_aware_success_state(run_state.failure_progress),
            blocked_reason=None,
        )
    )


async def _advance_review_ready(
    run_state: BehaviorContractRunState,
    dependencies: ReviewProgressionDependencies,
) -> RunAdvance:
    contract = run_state.contract
    cycle = run_state.current_cycle()
    if cycle is None or cycle.candidate_revision is None:
        raise ValueError("review_ready run state requires a candidate revision")
    review_material = _review_material(contract, run_state, cycle, dependencies.review_material_provider)
    review = await dependencies.reviewer.review(
        SemanticReviewRequest(contract, run_state, cycle, cycle.candidate_revision, review_material)
    )
    cycle = replace(cycle, review_result=review, review_history=[*cycle.review_history, review])
    if review.verdict != "approved":
        return _advance_nonapproved_review(run_state, contract, cycle, review, dependencies.max_semantic_repairs)
    return await _advance_approved_review(run_state, dependencies, contract, cycle)


async def _advance_approved_review(
    run_state: BehaviorContractRunState,
    dependencies: ReviewProgressionDependencies,
    contract: BehaviorContract,
    cycle: ContractCycleRecord,
) -> RunAdvance:
    split_resolution = approval_resolution(run_state, cycle.step)
    completed_refs = sorted(set(run_state.completed_requirement_refs).union(cycle.step.requirement_refs))
    current_pool = "approved"
    blocked_reason = None
    failure_progress = split_aware_success_state(run_state.failure_progress)
    contract_status = "approved"
    if split_resolution is not None:
        completed_refs = split_resolution.completed_requirement_refs
        current_pool = split_resolution.current_pool
        blocked_reason = split_resolution.blocked_reason
        failure_progress = split_resolution.failure_progress
        contract_status = current_pool
    approved_run_state = replace(
        run_state,
        current_pool=current_pool,
        contract=replace(contract, status=contract_status),
        semantic_base_revision=cycle.candidate_revision,
        repository_binding=run_state.repository_binding.with_base_sha(cycle.candidate_revision),
        completed_requirement_refs=completed_refs,
        blocked_reason=blocked_reason,
        cycles=_replace_current_cycle(run_state.cycles, replace(cycle, semantic_revision=cycle.candidate_revision, pool="approved")),
        failure_progress=failure_progress,
    )
    if split_resolution is not None and current_pool == "tdd_ready":
        return RunAdvance(approved_run_state)
    if approved_run_state.targeted_checklist_ref is None or dependencies.gatekeeper is None:
        return RunAdvance(approved_run_state)
    gatekeeper_state = await dependencies.gatekeeper.assess(
        GatekeeperAssessmentRequest(
            contract,
            approved_run_state,
            approved_run_state.gatekeeper_state
            or await dependencies.gatekeeper.ensure_state(GatekeeperStateRequest(contract, None)),
        )
    )
    return _targeted_checklist_completion(approved_run_state, contract, gatekeeper_state)


def _targeted_checklist_completion(
    approved_run_state: BehaviorContractRunState,
    contract: BehaviorContract,
    gatekeeper_state,
) -> RunAdvance:
    checklist_ref = approved_run_state.targeted_checklist_ref
    if checklist_ref is None:
        raise ValueError("targeted checklist completion requires a checklist ref")
    target_assessment = _checklist_assessment(gatekeeper_state, checklist_ref)
    target_proven = target_assessment is not None and target_assessment.status == "proven"
    checklist_complete = gatekeeper_state.is_complete()
    pool = "completed" if checklist_complete else ("approved" if target_proven else "replan_ready")
    status = "completed" if checklist_complete else approved_run_state.contract.status
    reason = None if checklist_complete else (
        "additional specification checklist items remain unproven"
        if target_proven
        else "targeted specification gap remains unproven"
    )
    return RunAdvance(
        replace(
            approved_run_state,
            current_pool=pool,
            contract=replace(contract, status=status),
            blocked_reason=reason,
            gatekeeper_state=gatekeeper_state,
        ),
        return_now=True,
    )


async def _advance_repair_ready(
    run_state: BehaviorContractRunState,
    dependencies: RepairProgressionDependencies,
) -> RunAdvance:
    contract = run_state.contract
    cycle = run_state.current_cycle()
    if cycle is None or cycle.review_result is None or cycle.candidate_revision is None:
        raise ValueError("repair_ready run state requires a review result and candidate revision")
    work_unit = dependencies.repair_factory.build(RepairWorkUnitBuildRequest(contract, cycle, cycle.review_result))
    outcome = await dependencies.phase_executor.execute(
        PhaseExecutionRequest(TddPhase.GREEN, work_unit, run_state.repository_binding.with_base_sha(cycle.candidate_revision))
    )
    if not outcome.accepted:
        return RunAdvance(
            replace(
                run_state,
                current_pool="replan_ready",
                contract=replace(contract, status="replan_ready"),
                blocked_reason=outcome.blocked_reason,
                cycles=_replace_current_cycle(run_state.cycles, replace(cycle, pool="replan_ready", green_phase=outcome.phase_state)),
            ),
            return_now=True,
        )
    updated_cycle = replace(
        cycle,
        repair_attempts=cycle.repair_attempts + 1,
        green_phase=outcome.phase_state,
        candidate_revision=outcome.phase_state.accepted_revision,
        pool="review_ready",
    )
    return RunAdvance(
        replace(
            run_state,
            current_pool="review_ready",
            contract=replace(contract, status="review_ready"),
            cycles=_replace_current_cycle(run_state.cycles, updated_cycle),
            failure_progress=split_aware_success_state(run_state.failure_progress),
            blocked_reason=None,
        )
    )


@dataclass(frozen=True)
class CycleActiveProgressor:
    dependencies: CycleProgressionDependencies

    async def advance(self, run_state: BehaviorContractRunState) -> RunAdvance:
        return await _advance_cycle_active(run_state, self.dependencies)


@dataclass(frozen=True)
class ReviewReadyProgressor:
    dependencies: ReviewProgressionDependencies

    async def advance(self, run_state: BehaviorContractRunState) -> RunAdvance:
        return await _advance_review_ready(run_state, self.dependencies)


@dataclass(frozen=True)
class RepairReadyProgressor:
    dependencies: RepairProgressionDependencies

    async def advance(self, run_state: BehaviorContractRunState) -> RunAdvance:
        return await _advance_repair_ready(run_state, self.dependencies)


class BehaviorContractCoordinator:
    def __init__(self, dependencies: CoordinatorDependencies | None = None, **legacy):
        self.dependencies = dependencies or CoordinatorDependencies(**legacy)
        deps = self.dependencies
        self.repository_binding = deps.repository_binding
        state_repo = deps.state_repo or TddStateRepo()
        repository_material_provider = deps.repository_material_provider or _default_tester_repository_material_provider(deps.repository_binding)
        step_planner = deps.step_planner or DynamicTddPlanner(deps.reasoning_gateway, repository_material_provider=repository_material_provider)
        reviewer = deps.reviewer or SeniorReviewer(deps.reasoning_gateway)
        tester_factory = deps.tester_factory or ContractTesterWorkUnitFactory()
        developer_factory = deps.developer_factory or ContractDeveloperWorkUnitFactory()
        repair_factory = deps.repair_factory or ContractRepairWorkUnitFactory()
        review_material_provider = deps.review_material_provider or _default_review_material_provider(deps.repository_binding)
        failure_policy = deps.failure_policy or FailureProgressionPolicy()
        dependency_planner = deps.dependency_planner or DependencyPrerequisitePlanner(deps.reasoning_gateway)
        self.run_store = ContractRunStore(state_repo)
        phase_executor = PhaseExecutor(deps.execution_gateway)
        split_planner = deps.split_planner or ResourceLimitSplitPlanner(deps.reasoning_gateway)
        policy_scope_resolver = deps.policy_scope_resolver or PolicyScopeViolationResolver()
        failure_router = FailedCandidateRouter(FailureRouterDependencies(failure_policy, deps.environment_recovery, dependency_planner, split_planner, repository_material_provider, deps.max_tester_repairs, deps.max_developer_repairs, policy_scope_resolver))
        self.ready_progressor = ReadyPoolProgressor(ReadyPoolDependencies(step_planner, deps.gatekeeper, deps.gap_adapter, deps.repository_binding))
        self.cycle_progressor = CycleActiveProgressor(CycleProgressionDependencies(tester_factory, developer_factory, repository_material_provider, phase_executor, failure_router))
        self.review_progressor = ReviewReadyProgressor(ReviewProgressionDependencies(reviewer, review_material_provider, deps.gatekeeper, deps.max_semantic_repairs))
        self.repair_progressor = RepairReadyProgressor(RepairProgressionDependencies(repair_factory, phase_executor))

    async def run_contract(self, contract: BehaviorContract) -> BehaviorContractCoordinationResult:
        snapshot = self.run_store.load(contract.project_id) or self.run_store.initial(contract.project_id, self.repository_binding)
        run_state = snapshot.contract_runs.get(contract.id)
        if run_state is None:
            run_state = BehaviorContractRunState(contract=contract, repository_binding=self.repository_binding, semantic_base_revision=self.repository_binding.base_sha)
            snapshot = self.run_store.save(snapshot, run_state)
        while True:
            contract = run_state.contract
            if run_state.current_pool in TERMINAL_CONTRACT_POOLS:
                return _result_from_run_state(run_state)
            advance = await self._advance(run_state)
            run_state = advance.run_state
            snapshot = self.run_store.save(snapshot, run_state)
            if advance.return_now:
                return _result_from_run_state(run_state)

    async def _advance(self, run_state: BehaviorContractRunState) -> RunAdvance:
        if run_state.current_pool in {"tdd_ready", "approved"}:
            return await self.ready_progressor.advance(run_state)
        if run_state.current_pool == "cycle_active":
            return await self.cycle_progressor.advance(run_state)
        if run_state.current_pool == "review_ready":
            return await self.review_progressor.advance(run_state)
        if run_state.current_pool == "repair_ready":
            return await self.repair_progressor.advance(run_state)
        raise ValueError(f"unsupported contract run pool: {run_state.current_pool}")


def _require_run_state(run_state: BehaviorContractRunState | None) -> BehaviorContractRunState:
    if run_state is None:
        raise ValueError("run state is required")
    return run_state


def _replace_current_cycle(cycles: list[ContractCycleRecord], replacement: ContractCycleRecord) -> list[ContractCycleRecord]:
    if not cycles:
        raise ValueError("expected at least one cycle to replace")
    return [*cycles[:-1], replacement]


def _result_from_run_state(run_state: BehaviorContractRunState) -> BehaviorContractCoordinationResult:
    return BehaviorContractCoordinationResult(
        contract_id=run_state.contract.id,
        current_binding=run_state.repository_binding.with_base_sha(run_state.semantic_base_revision),
        semantic_revision=run_state.semantic_base_revision,
        current_pool=run_state.current_pool,
        cycles=list(run_state.cycles),
        completed_requirement_refs=list(run_state.completed_requirement_refs),
        blocked_reason=run_state.blocked_reason,
    )


def _split_requirement(
    contract: BehaviorContract,
    step: TddStepProposal,
) -> BehaviorContractRequirement:
    if len(step.requirement_refs) != 1:
        raise ValueError("resource-limit split requires exactly one requirement ref")
    requirement_ref = step.requirement_refs[0]
    for requirement in contract.observable_requirements:
        if requirement.ref == requirement_ref:
            return requirement
    raise ValueError(f"unknown split requirement ref: {requirement_ref}")


def _repository_material(
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    provider: TesterRepositoryMaterialProvider | None,
    revision: str | None = None,
) -> dict[str, object] | None:
    if provider is None:
        return None
    return provider.render(RepositoryMaterialRequest(contract, run_state, revision))


def _review_material(
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    provider: ReviewMaterialProvider | None,
) -> str:
    if provider is None:
        raise ValueError("semantic review requires a repository review material provider or registered repository root")
    return provider.render(ReviewMaterialRequest(contract, run_state, cycle))


def _cycle_with_phase_state(
    cycle: ContractCycleRecord,
    phase: TddPhase,
    phase_state,
    pool: str,
) -> ContractCycleRecord:
    updates = {"pool": pool, "red_phase" if phase is TddPhase.RED else "green_phase": phase_state}
    return replace(cycle, **updates)


async def _environment_recovery_succeeded(
    dependencies: FailureRouterDependencies,
    run_state: BehaviorContractRunState,
    project_id: str,
) -> bool:
    if dependencies.environment_recovery is None:
        return False
    return dependencies.failure_policy.retry_allowed(
        RetryBudget(state=run_state.failure_progress, route=RetryRoute.ENVIRONMENT_RECOVERY, budget=1)
    ) and await dependencies.environment_recovery.recover_and_verify(project_id)


def _completed_run_state(run_state: BehaviorContractRunState) -> BehaviorContractRunState:
    contract = run_state.contract
    return replace(
        run_state,
        current_pool="completed",
        completed_requirement_refs=_ordered_completed_requirement_refs(contract, run_state.completed_requirement_refs),
        contract=replace(contract, status="completed"),
        repository_binding=run_state.repository_binding.with_base_sha(run_state.semantic_base_revision),
    )


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
                        "kind": "behavior|validation|invariant|constraint|quality",
                        "evidence_kind": "test|mechanical|review",
                    }
                ]
            },
            "rules": [
                "one source obligation per clause",
                "do not bundle unrelated behaviors into one clause",
                "preserve happy-path, failure, query, and state-preservation obligations",
                "preserve constraint and quality obligations from the source text",
                "kind must be one of behavior, validation, invariant, constraint, quality",
                "evidence_kind must be one of test, mechanical, review",
                "use test for executable behavior and validation obligations by default",
                "use review for readability and unnecessary-abstraction obligations",
                "for quality clauses, evidence_kind must be review and must never be quality",
                "use mechanical for deterministic environment or dependency constraints",
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
                "kind": "behavior|validation|invariant|constraint|quality",
                "evidence_kind": "test|mechanical|review",
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
                "depends_on": ["requirement ref"],
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
                "declare depends_on only for a real prerequisite requirement in this contract; use an empty array when independently executable",
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



def _contract_from_response(
    text: str,
    *,
    label: str,
    allowed_production_paths: list[str],
    allowed_test_paths: list[str],
) -> BehaviorContract:
    return BehaviorContract.from_dict(
        _json_object(text, label=label),
        BehaviorContractLoadOptions(
            allowed_production_paths=allowed_production_paths,
            allowed_test_paths=allowed_test_paths,
        ),
    )


def _is_recoverable_contract_error(error: ValueError) -> bool:
    message = str(error)
    return message.startswith("source clauses must be covered by observable requirements:")


def _contract_repair_prompt(
    *,
    project_id: str,
    requirement_text: str,
    source_clauses: list[SourceRequirementClause],
    production_paths: list[str],
    test_paths: list[str],
    invalid_contract_text: str,
    validation_error: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Repair the invalid ATHBA behavior contract. Return raw JSON only.",
            "project_id": project_id,
            "requirement_text": requirement_text,
            "source_clauses": [clause.to_dict() for clause in source_clauses],
            "production_paths": production_paths,
            "test_paths": test_paths,
            "invalid_contract_draft": invalid_contract_text,
            "validation_error": validation_error,
            "required_json_schema": {
                "id": "string",
                "project_id": "string",
                "component_name": "string",
                "capability": "string",
                "requirement_source": "string",
                "source_clauses": [
                    {
                        "ref": "string",
                        "text": "string",
                        "kind": "behavior|validation|invariant|constraint|quality",
                        "evidence_kind": "test|mechanical|review",
                    }
                ],
                "observable_requirements": [
                    {
                        "ref": "string",
                        "source_refs": ["string"],
                        "summary": "string",
                        "observable_outcome": "string",
                        "test_hint": "string",
                        "error_expectation": "string|null",
                        "preserves_state_on_failure": "boolean",
                        "depends_on": ["requirement ref"],
                    }
                ],
                "invariants": ["string"],
                "production_paths": ["string"],
                "test_paths": ["string"],
                "public_api": ["string"],
                "error_semantics": ["string"],
                "non_goals": ["string"],
                "completion_criteria": ["string"],
                "status": "tdd_ready|cycle_active|review_ready|repair_ready|replan_ready|approved|completed|blocked_executor|blocked_environment|blocked_architecture|blocked_ambiguity|blocked_unclassified|split_required",
            },
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
            "repair_rules": [
                "keep the contract within the supplied repository-relative production and test paths",
                "preserve valid existing fields where possible",
                "every source clause ref must appear in at least one observable_requirements[].source_refs entry",
                "do not drop source clauses to hide coverage problems",
                "do not invent worker ids, model ids, GPU ids, endpoints, ports, or backend selection",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _step_prompt(
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    repository_material: dict[str, object] | None,
) -> str:
    prior_steps = [cycle.step.to_dict() for cycle in run_state.cycles]
    return json.dumps(
        {
            "instruction": "Act as ATHBA's Tester planner. Return one JSON object only.",
            "contract": contract.to_dict(),
            "allowed_requirement_refs": [
                ref
                for ref in run_state.active_requirement_refs()
                if ref in contract.ready_requirement_refs(run_state.completed_requirement_refs)
            ],
            "current_pool": run_state.current_pool,
            "completed_requirement_refs": run_state.completed_requirement_refs,
            "prior_steps": prior_steps,
            "repository_material": repository_material,
            "required_output": {
                "status": "propose|complete",
                "rationale": "string",
                "proposal": {
                    "step_id": "string",
                    "requirement_refs": ["copy exactly one value from allowed_requirement_refs"],
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
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
            "rules": [
                "do not repeat already covered requirements",
                "do not combine unrelated new behaviors into one proposal",
                "do not include implementation details",
                "do not leak worker, GPU, model, endpoint, or port data",
                "proposal.requirement_refs must copy exactly one value from allowed_requirement_refs",
                "proposal.test_name must be a full pytest node id that starts with proposal.test_path followed by ::",
                "use only modules and files visible in repository_material; this is an external repository, not ATHBA",
                "derive imports from the supplied production material and do not invent ATHBA imports or paths",
                "propose one new test node, not a claim that an existing node already exists",
                "when repository_material.all_contract_files_empty is true, choose a bootstrap behavior that establishes the contract component or one minimal public API operation; do not start with a downstream validation that assumes prior state",
                "never declare completion unless all requirement refs are already semantically approved in persisted state",
            ],
        },
        indent=2,
        sort_keys=True,
    )



def _decision_from_response(
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    text: str,
    *,
    label: str,
) -> TddStepDecision:
    decision = TddStepDecision.from_dict(_json_object(text, label=label))
    return DynamicTddPlanner(None)._validate_decision(StepDecisionValidationRequest(contract, run_state, decision))  # type: ignore[arg-type]


def _is_recoverable_step_error(error: ValueError) -> bool:
    message = str(error)
    return message in {
        "step decision response was not valid JSON",
        "step proposal referenced a requirement outside the contract",
        "step proposal test name must be a pytest node id within the selected test path",
        "step proposal leaked ATHBA-internal module or path assumptions into an external repository",
    }


def _step_repair_prompt(
    *,
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    invalid_step_text: str,
    validation_error: str,
    repository_material: dict[str, object] | None,
) -> str:
    return json.dumps(
        {
            "instruction": "Repair the invalid ATHBA Tester step decision. Return raw JSON only.",
            "contract": contract.to_dict(),
            "allowed_requirement_refs": run_state.active_requirement_refs(),
            "current_pool": run_state.current_pool,
            "completed_requirement_refs": run_state.completed_requirement_refs,
            "prior_steps": [cycle.step.to_dict() for cycle in run_state.cycles],
            "repository_material": repository_material,
            "invalid_step_decision": invalid_step_text,
            "validation_error": validation_error,
            "required_output": {
                "status": "propose|complete",
                "rationale": "string",
                "proposal": {
                    "step_id": "string",
                    "requirement_refs": ["copy exactly one value from allowed_requirement_refs"],
                    "focused_behavior": "one smallest useful missing observable behavior",
                    "test_name": "full pytest node id beginning with test_path::",
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
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
            "repair_rules": [
                "proposal.requirement_refs must copy exactly one value from allowed_requirement_refs",
                "proposal.test_name must be a full pytest node id that starts with proposal.test_path followed by ::",
                "use only modules and files visible in repository_material; this is an external repository, not ATHBA",
                "derive imports from supplied production material and do not invent ATHBA imports or paths",
                "when repository_material.all_contract_files_empty is true, choose a bootstrap behavior that establishes the contract component or one minimal public API operation",
                "do not change the contract paths",
                "do not invent worker ids, model ids, GPU ids, endpoints, ports, or backend selection",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _is_valid_pytest_node_for_path(test_name: str, test_path: str) -> bool:
    prefix = f"{test_path}::"
    function_name = test_name.removeprefix(prefix)
    return test_name.startswith(prefix) and bool(re.fullmatch(r"test_[A-Za-z0-9_]+", function_name))


def _has_athba_internal_leakage(proposal: TddStepProposal) -> bool:
    text = json.dumps(proposal.to_dict(), sort_keys=True).lower()
    return any(fragment in text for fragment in ("athba.", "import athba", "from athba", "/athba/"))


def _empty_source_red_guidance(contract: BehaviorContract, repository_material: dict[str, object] | None) -> str:
    if not repository_material or not repository_material.get("all_contract_files_empty"):
        return ""
    production_files = repository_material.get("production_files", [])
    if not isinstance(production_files, list):
        return ""
    module_names = [
        item.get("module_name")
        for item in production_files
        if isinstance(item, dict) and isinstance(item.get("module_name"), str)
    ]
    if not module_names:
        return ""
    module_name = module_names[0]
    return (
        f"Visible contract files are empty. Use `import {module_name}` at module scope and resolve "
        f"`getattr({module_name}, {contract.component_name!r})` only inside the proposed test body. "
        f"Do not use `from {module_name} import {contract.component_name}`, because a missing component must fail as a test failure rather than a collection error. "
    )


def _python_module_name(path: str) -> str | None:
    normalized = _repository_relative_path(path, label="repository context path")
    if not normalized.endswith(".py"):
        return None
    return normalized[:-3].replace("/", ".")


def _pytest_nodes(path: str, content: str) -> list[str]:
    if not path.endswith(".py"):
        return []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    return [
        f"{path}::{node.name}"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    ]


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


def _tester_objective(
    contract: BehaviorContract,
    step: TddStepProposal,
    repository_material: dict[str, object] | None,
) -> str:
    return (
        "Act in ATHBA's Tester role during RED. "
        f"Work only within {step.test_path}. Preserve accepted tests. Add exactly one focused new pytest test named {step.test_name}. "
        f"Target behavior: {step.focused_behavior}. Expected observable result: {step.expected_result}. "
        f"Requirement refs: {', '.join(step.requirement_refs)}. "
        "Do not edit production code. Do not try to make the test pass. "
        "Make the test data actually satisfy the target behavior's precondition and invoke the operation that should produce the stated result; do not assert a failure using inputs that leave that condition untriggered. "
        "Do not add helper functions, fixtures, comments, or docstrings unless strictly required. "
        "This target is a standalone external repository, not ATHBA. Use only modules and files visible in the supplied repository material. "
        "Do not import ATHBA internals unless they are explicitly present in that material. "
        "The proposed pytest node must be created exactly. Keep imports collection-safe: when a visible module lacks the target API, import the module and access the missing API inside the test so RED fails during test execution, not collection. "
        f"{_empty_source_red_guidance(contract, repository_material)}"
        f"Contract component: {contract.component_name}. RED objective: {step.red_objective}. "
        f"Repository material: {json.dumps(repository_material, sort_keys=True)}"
    )


def _developer_objective(
    contract: BehaviorContract,
    step: TddStepProposal,
    repository_material: dict[str, object] | None,
) -> str:
    return (
        "Act in ATHBA's Developer role during GREEN. "
        f"Work only within {step.production_path}. Do not edit tests. The focused failing test is {step.test_name}. "
        f"Implement only enough code for this behavior: {step.focused_behavior}. Expected observable result: {step.expected_result}. "
        f"Requirement refs: {', '.join(step.requirement_refs)}. Preserve prior accepted behavior and keep the design small, direct, and readable. "
        "Do not introduce speculative abstractions, dead code, dead imports, noisy comments, or unrelated features. "
        "This target is a standalone external repository, not ATHBA. Use only modules and files visible in the supplied repository material. "
        f"Contract component: {contract.component_name}. GREEN objective: {step.green_objective}. "
        f"Repository material: {json.dumps(repository_material, sort_keys=True)}"
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


def _default_tester_repository_material_provider(
    repository_binding: RepositoryBinding,
) -> TesterRepositoryMaterialProvider | None:
    if repository_binding.registered_root is None:
        return None
    return GitTesterRepositoryMaterialProvider(repository_binding.registered_root)


def _repository_material_for_run_state(
    contract: BehaviorContract,
    run_state: BehaviorContractRunState,
    *,
    provider: TesterRepositoryMaterialProvider | None,
) -> dict[str, object] | None:
    resolved_provider = provider or _default_tester_repository_material_provider(run_state.repository_binding)
    if resolved_provider is None:
        return None
    return resolved_provider.render(RepositoryMaterialRequest(contract, run_state))


def _first_executable_gap(contract: BehaviorContract, gatekeeper_state):
    if gatekeeper_state.latest_assessment is None:
        return None
    source_by_ref = {clause.ref: clause for clause in contract.source_clauses}
    item_kinds = {item.ref: item.kind for item in gatekeeper_state.checklist.items}
    for gap in gatekeeper_state.latest_assessment.gaps:
        if item_kinds.get(gap.checklist_ref) not in {"behavior", "validation", "invariant"}:
            continue
        if gap.checklist_ref in source_by_ref:
            return gap
        normalized_gap = " ".join(gap.obligation_text.lower().split())
        if any(" ".join(clause.text.lower().split()) == normalized_gap for clause in contract.source_clauses):
            return gap
    return None


def _has_untraceable_executable_gap(gatekeeper_state) -> bool:
    if gatekeeper_state.latest_assessment is None:
        return False
    item_kinds = {item.ref: item.kind for item in gatekeeper_state.checklist.items}
    return any(item_kinds.get(gap.checklist_ref) in {"behavior", "validation", "invariant"} for gap in gatekeeper_state.latest_assessment.gaps)


def _targeted_requirement_for_gap(contract: BehaviorContract, gap):
    prefix = f"GK-{gap.checklist_ref}-"
    return next(requirement for requirement in contract.observable_requirements if requirement.ref.startswith(prefix))


def _checklist_assessment(gatekeeper_state, checklist_ref: str):
    if gatekeeper_state.latest_assessment is None:
        return None
    return next(
        (assessment for assessment in gatekeeper_state.latest_assessment.item_assessments if assessment.checklist_ref == checklist_ref),
        None,
    )


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


def _is_red_already_satisfied_from_phase(outcome: PhaseOutcome) -> bool:
    if outcome.phase_state.status != "already_satisfied":
        return False
    return RED_ALREADY_SATISFIED_FRAGMENT in (outcome.phase_state.error or "")



def _add_synthesized_prerequisite(
    contract: BehaviorContract,
    decision: DependencyDecision,
    run_state: BehaviorContractRunState,
) -> BehaviorContract:
    prerequisite_ref = decision.prerequisite_refs[0]
    if prerequisite_ref == decision.parent_requirement_ref or prerequisite_ref in contract.requirement_refs() or prerequisite_ref in run_state.completed_requirement_refs:
        raise ValueError("synthesized prerequisite ref must be new and distinct")
    prior = [item for item in run_state.failure_progress.dependency_decisions if item.disposition is DependencyDisposition.ADD_PREREQUISITE and item.parent_requirement_ref == decision.parent_requirement_ref]
    if len(prior) >= 3:
        raise ValueError("synthesized prerequisite depth limit exhausted")
    parent = next(item for item in contract.observable_requirements if item.ref == decision.parent_requirement_ref)
    observable = decision.prerequisite_observable or ""
    if len(observable.split()) < 3 or len(observable) > 300 or "\n" in observable:
        raise ValueError("synthesized prerequisite must be one bounded observable behavior")
    normalized = " ".join(observable.lower().split())
    if any(" ".join((item.prerequisite_observable or "").lower().split()) == normalized for item in prior):
        raise ValueError("equivalent prerequisite already exists for this parent lineage")
    prerequisite = BehaviorContractRequirement(
        ref=prerequisite_ref,
        source_refs=list(parent.source_refs),
        summary=observable,
        observable_outcome=observable,
        test_hint=f"prove_{prerequisite_ref.lower().replace('-', '_')}",
        error_expectation=None,
        preserves_state_on_failure=True,
        depends_on=list(parent.depends_on),
    )
    updated_parent = replace(parent, depends_on=[*parent.depends_on, prerequisite_ref])
    requirements = [updated_parent if item.ref == parent.ref else item for item in contract.observable_requirements]
    return replace(contract, observable_requirements=[*requirements, prerequisite])


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
