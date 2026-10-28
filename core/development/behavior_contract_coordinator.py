"""Contract-driven TDD lane for PR16 behavior-contract orchestration."""

from __future__ import annotations

import ast
import json
import re
import subprocess
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from traceback import extract_tb
from typing import Protocol, cast

from core.development.behavior_replan_domain import (
    BehaviorReplanCorrectionRequest, BehaviorReplanRequest, BehaviorReplanResponse,
)
from core.development.source_obligation_semantics import validate_planned_clauses
from core.development.required_public_signature import required_signatures, validate_clause_signatures
from core.development.behavior_replanning import BehaviorRequirementReplanner
from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.contract_run_store import ContractRunStore
from core.development.failure_progression import (
    DependencyDecision,
    DependencyDisposition,
    FailureClassification,
    FailureDecision,
    FailureObservation,
    FailureProgressState,
    FailureRouteState,
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
from core.development.tdd_progression_values import ContractPoolStatus
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
from core.development.specification_gap_adapter import matching_contract_source_refs_for_gap
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
from core.development.red_acceptance import RedAcceptanceDependencies, RedAcceptanceRequest, RedAcceptanceResult, RedAcceptanceService, RedBehaviorVerifier, fail_closed_red_acceptance_result, fallback_red_acceptance_result
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult
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


MAX_SOURCE_CLAUSE_SPLIT_DEPTH = 16
MAX_SOURCE_CLAUSE_SPLITS = 256
MAX_SOURCE_CLAUSE_CHILDREN = 32


@dataclass(frozen=True)
class SourceClausePlanningAttempt:
    response: str
    validation_error: str | None = None
    stage: str = "initial"
    validation_location: str | None = None
    validation_rule: str | None = None


@dataclass(frozen=True)
class SourceClausePlanningResult:
    clauses: list[SourceRequirementClause]
    attempts: tuple[SourceClausePlanningAttempt, ...]


class SourceClausePlanningFailure(Exception):
    def __init__(
        self,
        attempts: tuple[SourceClausePlanningAttempt, ...],
        terminal_reason: str | None = None,
    ):
        if not attempts:
            raise ValueError("source clause planning failure requires at least one attempt")
        self.attempts = attempts
        self.terminal_reason = terminal_reason
        detail = "" if terminal_reason is None else f": {terminal_reason}"
        super().__init__("source requirement clause planning failed after bounded schema repair" + detail)


@dataclass(frozen=True)
class _SourceClauseValidationIssue:
    message: str
    location: str
    rule: str
    raw_clause: dict[str, object] | None = None
    clause_index: int | None = None

    @property
    def identity(self) -> tuple[str, str]:
        return self.location, self.rule

    @property
    def can_target_repair(self) -> bool:
        if self.raw_clause is None or self.clause_index is None:
            return False
        return all(
            isinstance(value := self.raw_clause.get(field), str) and value.strip()
            for field in ("ref", "source_quote")
        )

    @property
    def can_split(self) -> bool:
        if self.raw_clause is None or self.clause_index is None:
            return False
        return all(
            isinstance(value := self.raw_clause.get(field), str) and value.strip()
            for field in ("ref", "text", "source_quote", "subject")
        )


class _SourceClauseValidationError(ValueError):
    def __init__(self, issue: _SourceClauseValidationIssue):
        self.issue = issue
        super().__init__(issue.message)


@dataclass(frozen=True)
class _SourceClauseRepairRequest:
    project_id: str
    requirement_text: str
    invalid_response: str
    issue: _SourceClauseValidationIssue


@dataclass(frozen=True)
class _SourceClauseSplitRequest:
    project_id: str
    requirement_text: str
    issue: _SourceClauseValidationIssue


@dataclass(frozen=True)
class _SourceClauseSplitFormatRepairRequest:
    request: _SourceClauseSplitRequest
    invalid_response: str
    validation_error: str


class _SourceClauseSplitFormatError(ValueError):
    """The split reply is not structurally decodable; one format repair is allowed."""


@dataclass(frozen=True)
class _SourceClauseSplitResponse:
    disposition: str
    rationale: str
    children: tuple[dict[str, object], ...] = ()
    coverage_rationale: str = ""


@dataclass
class _SourceClauseSplitProgress:
    split_count: int = 0
    structures: set[str] = field(default_factory=set)
    ancestors_by_location: dict[str, tuple[str, ...]] = field(default_factory=dict)
    assigned_child_authority: dict[str, tuple[str, str]] = field(default_factory=dict)


class RequirementClausePlanner:
    """Turn one component requirement into machine-checkable source clauses."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def create_clauses(self, *, project_id: str, requirement_text: str) -> list[SourceRequirementClause]:
        return (await self.plan_clauses(project_id=project_id, requirement_text=requirement_text)).clauses

    async def plan_clauses(self, *, project_id: str, requirement_text: str) -> SourceClausePlanningResult:
        reasoning_request = ReasoningRequest(
            purpose="athba_source_requirement_clauses",
            prompt=_source_clause_prompt(project_id=project_id, requirement_text=requirement_text),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(reasoning_request)
        response = result.text
        locations = _source_clause_locations(response)
        attempts = [SourceClausePlanningAttempt(response, stage="initial")]
        corrected_errors: set[tuple[str, str]] = set()
        split_progress = _SourceClauseSplitProgress()
        while True:
            try:
                clauses = _validated_source_clause_response(response, requirement_text, locations)
            except _SourceClauseValidationError as error:
                issue = error.issue
                attempts[-1] = replace(
                    attempts[-1],
                    validation_error=issue.message,
                    validation_location=issue.location,
                    validation_rule=issue.rule,
                )
                if issue.identity not in corrected_errors:
                    corrected_errors.add(issue.identity)
                    invalid_response = response
                    repair_response = await self._repair_clauses(
                        _SourceClauseRepairRequest(
                            project_id=project_id,
                            requirement_text=requirement_text,
                            invalid_response=invalid_response,
                            issue=issue,
                        )
                    )
                    attempts.append(SourceClausePlanningAttempt(repair_response, stage="repair"))
                    try:
                        response = _apply_source_clause_repair(
                            previous_response=invalid_response,
                            issue=issue,
                            repair_response=repair_response,
                        )
                        locations = _repaired_source_clause_locations(
                            response,
                            invalid_response,
                            locations,
                            issue,
                            split_progress,
                        )
                    except ValueError as repair_error:
                        attempts[-1] = replace(
                            attempts[-1],
                            validation_error=str(repair_error),
                            validation_location=issue.location,
                            validation_rule=issue.rule,
                        )
                        raise SourceClausePlanningFailure(
                            tuple(attempts),
                            f"source clause repair failed: {repair_error}",
                        ) from repair_error
                    continue
                if not issue.can_split:
                    raise SourceClausePlanningFailure(
                        tuple(attempts),
                        _unresolved_source_clause_error_reason(issue),
                    ) from error
                split_request = _SourceClauseSplitRequest(
                    project_id=project_id,
                    requirement_text=requirement_text,
                    issue=issue,
                )
                split_result = await self._split_clause(split_request)
                attempts.append(
                    SourceClausePlanningAttempt(
                        split_result.text,
                        stage="split",
                        validation_error=issue.message,
                        validation_location=issue.location,
                        validation_rule=issue.rule,
                    )
                )
                try:
                    split = _decode_source_clause_split(split_result.text)
                except _SourceClauseSplitFormatError as format_error:
                    attempts[-1] = replace(attempts[-1], validation_error=str(format_error))
                    repaired_split_response = await self._repair_split_format(
                        _SourceClauseSplitFormatRepairRequest(
                            request=split_request,
                            invalid_response=split_result.text,
                            validation_error=str(format_error),
                        )
                    )
                    attempts.append(
                        SourceClausePlanningAttempt(
                            repaired_split_response,
                            stage="split_format_repair",
                            validation_location=issue.location,
                            validation_rule=issue.rule,
                        )
                    )
                    try:
                        _validate_source_clause_split_format_repair(
                            split_result.text,
                            repaired_split_response,
                        )
                        split = _decode_source_clause_split(repaired_split_response)
                    except ValueError as format_repair_error:
                        attempts[-1] = replace(
                            attempts[-1],
                            validation_error=str(format_repair_error),
                        )
                        raise SourceClausePlanningFailure(
                            tuple(attempts),
                            f"source clause split format repair failed: {format_repair_error}",
                        ) from format_repair_error
                except ValueError as split_decode_error:
                    attempts[-1] = replace(attempts[-1], validation_error=str(split_decode_error))
                    raise SourceClausePlanningFailure(
                        tuple(attempts),
                        f"source clause split failed: {split_decode_error}",
                    ) from split_decode_error
                try:
                    response, locations = _replace_invalid_clause_with_split(
                        response,
                        issue,
                        split,
                        split_progress,
                        locations,
                    )
                except ValueError as split_error:
                    attempts[-1] = replace(attempts[-1], validation_error=str(split_error))
                    raise SourceClausePlanningFailure(
                        tuple(attempts),
                        f"source clause split failed: {split_error}",
                    ) from split_error
                continue
            return SourceClausePlanningResult(clauses, tuple(attempts))

    async def _repair_clauses(self, repair: _SourceClauseRepairRequest) -> str:
        if repair.issue.can_target_repair:
            prompt = _source_clause_targeted_repair_prompt(
                project_id=repair.project_id,
                issue=repair.issue,
            )
        else:
            prompt = _source_clause_repair_prompt(
                project_id=repair.project_id,
                requirement_text=repair.requirement_text,
                invalid_response=repair.invalid_response,
                validation_error=repair.issue.message,
            )
        repair_request = ReasoningRequest(
            purpose="athba_source_requirement_clauses_repair",
            prompt=prompt,
            project_id=repair.project_id,
            requires_large_context=False,
        )
        return (await self.gateway.reason(repair_request)).text

    async def _split_clause(self, request: _SourceClauseSplitRequest) -> ReasoningResult:
        split_request = ReasoningRequest(
            purpose="athba_source_requirement_clause_split",
            prompt=_source_clause_split_prompt(
                project_id=request.project_id,
                requirement_text=request.requirement_text,
                offending_clause=request.issue.raw_clause or {},
                validation_error=request.issue.message,
            ),
            project_id=request.project_id,
            requires_large_context=False,
        )
        return await self.gateway.reason(split_request)

    async def _repair_split_format(
        self,
        repair: _SourceClauseSplitFormatRepairRequest,
    ) -> str:
        format_repair_request = ReasoningRequest(
            purpose="athba_source_requirement_clause_split_format_repair",
            prompt=_source_clause_split_format_repair_prompt(
                request=repair.request,
                invalid_response=repair.invalid_response,
                validation_error=repair.validation_error,
            ),
            project_id=repair.request.project_id,
            requires_large_context=False,
        )
        return (await self.gateway.reason(format_repair_request)).text


def _validated_source_clause_response(
    response: str,
    requirement_text: str,
    locations: tuple[str, ...],
) -> list[SourceRequirementClause]:
    entries = _raw_source_clause_entries(response)
    try:
        clauses = _decode_source_clauses(response)
    except (ValueError, KeyError, TypeError) as error:
        raise _SourceClauseValidationError(_decode_validation_issue(entries, locations, error)) from error
    try:
        validate_planned_clauses(clauses, requirement_text)
    except (ValueError, KeyError, TypeError) as error:
        issue = _planned_clause_validation_issue(entries, clauses, requirement_text, locations, error)
        raise _SourceClauseValidationError(issue) from error
    try:
        validate_clause_signatures(requirement_text, tuple(clause.text for clause in clauses))
    except (ValueError, KeyError, TypeError) as error:
        issue = _signature_validation_issue(requirement_text, clauses, error)
        raise _SourceClauseValidationError(issue) from error
    return clauses


def _raw_source_clause_entries(response: str) -> tuple[dict[str, object] | None, ...]:
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, dict) or not isinstance(payload.get("clauses"), list):
        return ()
    return tuple(
        None if not isinstance(item, dict) else dict(item)
        for item in payload["clauses"]
    )

def _source_clause_locations(response: str) -> tuple[str, ...]:
    return tuple(
        f"clause-slot:{index}"
        for index, _ in enumerate(_raw_source_clause_entries(response), 1)
    )


def _repaired_source_clause_locations(
    response: str,
    previous_response: str,
    previous: tuple[str, ...],
    issue: _SourceClauseValidationIssue,
    progress: _SourceClauseSplitProgress,
) -> tuple[str, ...]:
    if issue.clause_index is None:
        return _source_clause_locations(response)
    previous_entries = _raw_source_clause_entries(previous_response)
    current_entries = _raw_source_clause_entries(response)
    if len(current_entries) != len(previous_entries):
        raise ValueError("source clause repair changed the clause count outside the offending clause")
    if issue.clause_index >= len(current_entries):
        raise ValueError("source clause repair removed the offending clause")
    if any(
        current != previous_entry
        for index, (current, previous_entry) in enumerate(zip(current_entries, previous_entries))
        if index != issue.clause_index
    ):
        raise ValueError("source clause repair changed an unaffected clause")
    assigned = progress.assigned_child_authority.get(issue.location)
    current = current_entries[issue.clause_index]
    if assigned is not None and (
        not isinstance(current, dict)
        or current.get("ref") != assigned[0]
        or current.get("source_quote") != assigned[1]
    ):
        raise ValueError("source clause repair changed ATHBA-assigned child identity or source authority")
    return previous


def _apply_source_clause_repair(
    *,
    previous_response: str,
    issue: _SourceClauseValidationIssue,
    repair_response: str,
) -> str:
    if not issue.can_target_repair:
        return repair_response
    replacement = _decode_targeted_source_clause_repair(repair_response)
    entries = list(_raw_source_clause_entries(previous_response))
    if (
        issue.clause_index is None
        or issue.clause_index >= len(entries)
        or entries[issue.clause_index] != issue.raw_clause
    ):
        raise ValueError("source clause repair target changed before replacement")
    target = entries[issue.clause_index]
    if target is None:
        raise ValueError("source clause repair requires an identifiable offending clause")
    entries[issue.clause_index] = {**target, **replacement}
    return json.dumps({"clauses": entries}, sort_keys=True)


def _decode_targeted_source_clause_repair(response: str) -> dict[str, object]:
    payload = _json_object(response, label="targeted source clause repair")
    if "ref" in payload or "source_quote" in payload:
        raise ValueError("targeted source clause repair cannot alter stable clause identity or source authority")
    required_fields = {"text", "kind", "evidence_kind", "subject"}
    allowed_fields = required_fields | {"obligation_type"}
    if not required_fields.issubset(payload) or set(payload) - allowed_fields:
        raise ValueError("targeted source clause repair must return exactly one mutable clause object")
    if any(
        not isinstance(value := payload.get(field), str) or not value.strip()
        for field in required_fields
    ):
        raise ValueError("targeted source clause repair fields must be non-empty strings")
    if "obligation_type" in payload and not isinstance(payload["obligation_type"], str):
        raise ValueError("targeted source clause repair obligation_type must be a string")
    return dict(payload)


def _source_clause_location_at(locations: tuple[str, ...], index: int) -> str:
    return locations[index] if index < len(locations) else f"clause-slot:{index + 1}"


def _decode_validation_issue(
    entries: tuple[dict[str, object] | None, ...],
    locations: tuple[str, ...],
    error: Exception,
) -> _SourceClauseValidationIssue:
    for index, entry in enumerate(entries):
        if entry is None:
            return _source_clause_validation_issue(
                error,
                None,
                index,
                location=_source_clause_location_at(locations, index),
            )
        try:
            SourceRequirementClause.from_dict(entry)
        except (ValueError, KeyError, TypeError) as clause_error:
            return _source_clause_validation_issue(
                clause_error,
                entry,
                index,
                message=str(error),
                location=_source_clause_location_at(locations, index),
            )
    return _source_clause_validation_issue(error)


def _planned_clause_validation_issue(
    entries: tuple[dict[str, object] | None, ...],
    clauses: list[SourceRequirementClause],
    requirement_text: str,
    locations: tuple[str, ...],
    error: Exception,
) -> _SourceClauseValidationIssue:
    for index, clause in enumerate(clauses):
        try:
            validate_planned_clauses([clause], requirement_text)
        except (ValueError, KeyError, TypeError) as clause_error:
            entry = entries[index] if index < len(entries) else clause.to_dict()
            return _source_clause_validation_issue(
                clause_error,
                entry,
                index,
                message=str(error),
                location=_source_clause_location_at(locations, index),
            )
    return _source_clause_validation_issue(error)


def _signature_validation_issue(
    requirement_text: str,
    clauses: list[SourceRequirementClause],
    error: Exception,
) -> _SourceClauseValidationIssue:
    location = "document"
    try:
        for signature in required_signatures(requirement_text):
            if not any(signature.source_quote in clause.text for clause in clauses):
                digest = sha256(signature.source_quote.encode()).hexdigest()[:16]
                location = f"source-signature:{digest}"
                break
    except (ValueError, KeyError, TypeError):
        pass
    return _source_clause_validation_issue(error, location=location)


def _source_clause_validation_issue(
    error: Exception,
    entry: dict[str, object] | None = None,
    index: int | None = None,
    location: str | None = None,
    message: str | None = None,
) -> _SourceClauseValidationIssue:
    location = location or _source_clause_location(entry, index)
    detail = str(error) if message is None else message
    rule = _source_clause_validation_rule(error)
    return _SourceClauseValidationIssue(
        detail,
        location,
        rule,
        entry,
        index,
    )


def _source_clause_location(entry: dict[str, object] | None, index: int | None) -> str:
    return "document" if index is None else f"clause-slot:{index + 1}"


def _source_clause_validation_rule(
    error: Exception,
) -> str:
    chain = _exception_chain(error)
    field = _source_clause_error_field(" ".join(str(candidate) for candidate in chain))
    for candidate in reversed(chain):
        frames = extract_tb(candidate.__traceback__)
        for frame in reversed(frames):
            if "/core/" in frame.filename.replace("\\", "/"):
                origin = f"{Path(frame.filename).stem}:{frame.name}:{frame.lineno}"
                return f"{origin}:{field}"
    return f"{type(error).__name__}:{field}"


def _exception_chain(error: Exception) -> tuple[Exception, ...]:
    chain: list[Exception] = []
    current: Exception | None = error
    while current is not None and current not in chain:
        chain.append(current)
        next_error = current.__cause__ or current.__context__
        current = next_error if isinstance(next_error, Exception) else None
    return tuple(chain)


def _unresolved_source_clause_error_reason(issue: _SourceClauseValidationIssue) -> str:
    return (
        "behavior validator argument unresolved after its one correction "
        f"at {issue.location} rule {issue.rule}"
    )


def _replace_invalid_clause_with_split(
    response: str,
    issue: _SourceClauseValidationIssue,
    split: _SourceClauseSplitResponse,
    progress: _SourceClauseSplitProgress,
    locations: tuple[str, ...],
) -> tuple[str, tuple[str, ...]]:
    if split.disposition == "not_produced":
        raise ValueError(f"source clause split not produced: {split.rationale}")
    if issue.raw_clause is None or issue.clause_index is None:
        raise ValueError("source clause split requires an identifiable offending clause")
    entries = list(_raw_source_clause_entries(response))
    if issue.clause_index >= len(entries) or entries[issue.clause_index] != issue.raw_clause:
        raise ValueError("source clause split parent changed before replacement")
    children = _source_clause_split_children(issue.raw_clause, split)
    child_locations = tuple(
        f"{issue.location}/S{index:03d}" for index in range(1, len(children) + 1)
    )
    _validate_source_clause_split(
        issue.raw_clause,
        children,
        entries,
        progress,
        issue.location,
        child_locations,
    )
    entries[issue.clause_index:issue.clause_index + 1] = children
    next_locations = locations[:issue.clause_index] + child_locations + locations[issue.clause_index + 1:]
    return json.dumps({"clauses": entries}, sort_keys=True), next_locations


def _decode_source_clause_split(response: str) -> _SourceClauseSplitResponse:
    try:
        payload = _json_object(response, label="source clause split")
    except ValueError as error:
        raise _SourceClauseSplitFormatError(str(error)) from error
    disposition = payload.get("disposition")
    rationale = payload.get("rationale")
    if disposition not in {"split", "not_produced"} or not isinstance(rationale, str) or not rationale.strip():
        raise _SourceClauseSplitFormatError("source clause split requires a disposition and rationale")
    if disposition == "not_produced":
        if payload.get("children") not in (None, []):
            raise ValueError("not_produced source clause split cannot contain children")
        return _SourceClauseSplitResponse(disposition, rationale)
    coverage = payload.get("coverage_rationale")
    children = payload.get("children")
    if not isinstance(coverage, str) or not coverage.strip() or not isinstance(children, list):
        raise _SourceClauseSplitFormatError("source clause split requires coverage rationale and children")
    if not 2 <= len(children) <= MAX_SOURCE_CLAUSE_CHILDREN:
        raise ValueError("source clause split child count outside configured safety budget")
    return _SourceClauseSplitResponse(
        disposition,
        rationale,
        tuple(_source_clause_split_child(item) for item in children),
        coverage,
    )

def _source_clause_split_child(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _SourceClauseSplitFormatError("source clause split children must be objects")
    child = dict(value)
    allowed = {"text", "kind", "evidence_kind", "source_quote", "subject", "obligation_type"}
    if set(child) - allowed:
        raise _SourceClauseSplitFormatError("source clause split children cannot assign refs or unknown fields")
    return child


@dataclass(frozen=True)
class _RecoveredSourceClauseSplit:
    disposition: str
    children: tuple[tuple[str, ...], ...] | None


def _recover_source_clause_split(response: str) -> _RecoveredSourceClauseSplit | None:
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    disposition = payload.get("disposition")
    if disposition not in {"split", "not_produced"}:
        return None
    children = payload.get("children")
    if not isinstance(children, list) or not all(isinstance(child, dict) for child in children):
        return _RecoveredSourceClauseSplit(disposition, None)
    fields = ("text", "kind", "evidence_kind", "source_quote", "subject", "obligation_type")
    return _RecoveredSourceClauseSplit(
        disposition,
        tuple(
            tuple(
                json.dumps(child.get(field), sort_keys=True, separators=(",", ":"))
                for field in fields
            )
            for child in children
        ),
    )


def _validate_source_clause_split_format_repair(
    invalid_response: str,
    repaired_response: str,
) -> None:
    original = _recover_source_clause_split(invalid_response)
    if original is None:
        return
    repaired = _recover_source_clause_split(repaired_response)
    if repaired is None or repaired.disposition != original.disposition:
        raise ValueError("source clause split format repair changed the original disposition")
    if original.children is not None and repaired.children != original.children:
        raise ValueError("source clause split format repair changed the original children")


def _source_clause_split_children(
    parent: dict[str, object],
    split: _SourceClauseSplitResponse,
) -> list[dict[str, object]]:
    parent_ref = parent.get("ref")
    if not isinstance(parent_ref, str) or not parent_ref.strip():
        raise ValueError("source clause split parent requires a ref")
    return [
        {"ref": f"{parent_ref}-S{index:03d}", **child}
        for index, child in enumerate(split.children, 1)
    ]


def _validate_source_clause_split(
    parent: dict[str, object],
    children: list[dict[str, object]],
    entries: list[dict[str, object] | None],
    progress: _SourceClauseSplitProgress,
    parent_location: str,
    child_locations: tuple[str, ...],
) -> None:
    parent_ref = str(parent["ref"])
    ancestors = progress.ancestors_by_location.get(parent_location, ())
    if progress.split_count >= MAX_SOURCE_CLAUSE_SPLITS:
        raise ValueError("source clause split safety budget exhausted")
    if len(ancestors) >= MAX_SOURCE_CLAUSE_SPLIT_DEPTH:
        raise ValueError("source clause split depth exhausted")
    parent_shape = _source_clause_shape(parent)
    child_shapes = tuple(_source_clause_shape(child) for child in children)
    if parent_shape in child_shapes:
        raise ValueError("source clause split contains a child identical to its parent")
    if len(set(child_shapes)) != len(child_shapes):
        raise ValueError("source clause split contains duplicate children")
    if set(child_shapes).intersection(ancestors):
        raise ValueError("source clause split contains a child repeating an ancestor")
    structure = sha256(json.dumps((parent_shape, sorted(child_shapes))).encode()).hexdigest()
    if structure in progress.structures:
        raise ValueError("source clause split repeats a prior split structure")
    _validate_split_source_authority(parent, children)
    _validate_split_progress(parent, children)
    _validate_split_refs(parent_ref, children, entries)
    progress.split_count += 1
    progress.structures.add(structure)
    child_ancestors = ancestors + (parent_shape,)
    for location, child in zip(child_locations, children):
        progress.ancestors_by_location[location] = child_ancestors
        progress.assigned_child_authority[location] = (str(child["ref"]), str(child["source_quote"]))


def _validate_split_source_authority(
    parent: dict[str, object],
    children: list[dict[str, object]],
) -> None:
    parent_quote = _normalized_source_clause_text(parent.get("source_quote"))
    if not parent_quote:
        raise ValueError("source clause split parent requires a source passage")
    if any(_normalized_source_clause_text(child.get("source_quote")) != parent_quote for child in children):
        raise ValueError("source clause split children must retain the parent source passage")


def _validate_split_progress(
    parent: dict[str, object],
    children: list[dict[str, object]],
) -> None:
    parent_terms = _source_clause_terms(parent)
    child_terms = [_source_clause_terms(child) for child in children]
    if not parent_terms or not parent_terms.issubset(set().union(*child_terms)):
        raise ValueError("source clause split does not preserve the parent obligation wording")
    if any(not terms.issubset(parent_terms) for terms in child_terms):
        raise ValueError("source clause split introduces wording outside the parent obligation")
    if any(parent_terms.issubset(terms) for terms in child_terms):
        raise ValueError("source clause split contains a child that reproduces the parent obligation")


def _validate_split_refs(
    parent_ref: str,
    children: list[dict[str, object]],
    entries: list[dict[str, object] | None],
) -> None:
    expected = [f"{parent_ref}-S{index:03d}" for index in range(1, len(children) + 1)]
    if [str(child["ref"]) for child in children] != expected:
        raise ValueError("source clause split child refs are not deterministic")
    existing = {
        str(entry["ref"])
        for entry in entries
        if entry is not None and isinstance(entry.get("ref"), str)
    }
    existing.discard(parent_ref)
    if existing.intersection(expected):
        raise ValueError("source clause split child ref collides with an existing clause")


def _source_clause_shape(clause: dict[str, object]) -> str:
    fields = ("text", "kind", "evidence_kind", "source_quote", "subject", "obligation_type")
    content = [_normalized_source_clause_text(clause.get(field)) for field in fields]
    return sha256(json.dumps(content).encode()).hexdigest()


def _source_clause_terms(clause: dict[str, object]) -> set[str]:
    ignored = {"a", "an", "and", "or", "of", "the", "to"}
    text = str(clause.get("text", ""))
    return set(re.findall(r"\w+", text.casefold())) - ignored


def _normalized_source_clause_text(value: object) -> str:
    return " ".join(re.findall(r"\w+", str(value).casefold()))


class BehaviorContractPlanner:
    """Turn one component requirement into a structured provider-neutral contract."""

    def __init__(self, gateway: ReasoningGateway, clause_planner: RequirementClausePlanner | None = None):
        self.gateway = gateway
        self.clause_planner = clause_planner or RequirementClausePlanner(gateway)

    async def replan_requirement(self, request: BehaviorReplanRequest) -> BehaviorReplanResponse:
        return await BehaviorRequirementReplanner(self.gateway).replan(request)

    async def correct_replan_requirement(
        self,
        correction: BehaviorReplanCorrectionRequest,
    ) -> BehaviorReplanResponse:
        return await BehaviorRequirementReplanner(self.gateway).correct(correction)

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
                project_id=request.project_id,
                requirement_text=request.requirement_text,
                source_clauses=source_clauses,
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
                project_id=request.project_id,
                requirement_text=request.requirement_text,
                source_clauses=source_clauses,
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
        validation_error: str | None = None
        try:
            return _dependency_decision_from_response(request, result.text, label="dependency decision")
        except ValueError as error:
            if not _is_recoverable_dependency_error(error):
                raise
            validation_error = str(error)
        repaired = await self.gateway.reason(
            ReasoningRequest(
                purpose="athba_dependency_prerequisite_decision_repair",
                project_id=request.contract.project_id,
                requires_large_context=False,
                prompt=_dependency_decision_repair_prompt(
                    request=request,
                    invalid_decision_text=result.text,
                    validation_error=validation_error or "dependency decision response was not valid JSON",
                ),
            )
        )
        return _dependency_decision_from_response(
            request,
            repaired.text,
            label="dependency decision repair",
        )


def _semantic_review_from_response(
    request: SemanticReviewRequest,
    text: str,
    *,
    label: str,
) -> SemanticReviewResult:
    review = SemanticReviewResult.from_dict(_json_object(text, label=label))
    if review.candidate_revision != request.candidate_revision:
        raise ValueError("semantic review candidate revision mismatch")
    if review.step_id != request.cycle.step.step_id:
        raise ValueError("semantic review step id mismatch")
    out_of_scope_refs = _out_of_scope_review_source_refs(request, review)
    if out_of_scope_refs:
        raise ValueError(
            "semantic review referenced source evidence outside the active review scope"
        )
    return review


def _dependency_decision_from_response(
    request: DependencyDecisionRequest,
    text: str,
    *,
    label: str,
) -> DependencyDecision:
    decision = DependencyDecision.from_dict(_json_object(text, label=label))
    if decision.parent_requirement_ref != request.step.requirement_refs[0]:
        raise ValueError("dependency decision must retain the blocked requirement")
    if decision.disposition is DependencyDisposition.ALREADY_PLANNED:
        known = set(request.contract.requirement_refs())
        if not set(decision.prerequisite_refs).issubset(known):
            raise ValueError("existing planned dependency must reference contract requirements")
    if decision.disposition is DependencyDisposition.ADD_PREREQUISITE and len(decision.prerequisite_refs) != 1:
        raise ValueError("a justified prerequisite decision must add one smallest prerequisite")
    return decision


def _is_recoverable_dependency_error(error: ValueError) -> bool:
    return str(error) in {
        "dependency decision response was not valid JSON",
        "accepted dependency decisions require prerequisites",
        "existing planned dependency must reference contract requirements",
        "a justified prerequisite decision must add one smallest prerequisite",
    }


def _is_recoverable_semantic_review_error(error: ValueError) -> bool:
    return str(error) in {
        "semantic review response was not valid JSON",
        "semantic review referenced source evidence outside the active review scope",
    }



def _semantic_review_repair_prompt(
    *,
    request: SemanticReviewRequest,
    invalid_review_text: str,
    validation_error: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Repair the invalid ATHBA semantic review result. Return raw JSON only.",
            "project_id": request.contract.project_id,
            "candidate_revision": request.candidate_revision,
            "step": request.cycle.step.to_dict(),
            "review_scope": _semantic_review_scope(request),
            "invalid_review_draft": invalid_review_text,
            "validation_error": validation_error,
            "required_json_schema": {
                "verdict": "approved|repair_required|replan_required",
                "rationale": "string",
                "findings": ["string"],
                "candidate_revision": request.candidate_revision,
                "step_id": request.cycle.step.step_id,
                "evidence_refs": ["string"],
                "repair_instructions": ["string"],
            },
            "rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not add commentary before or after the JSON",
                "preserve the exact candidate_revision",
                "preserve the exact step_id",
                "review only the active step requirement refs plus already semantically approved requirement refs",
                "do not require future unmet contract requirements or unrelated public API work in this review result",
                "if you cite contract source refs in evidence_refs, they must come only from review_scope.allowed_source_refs",
                "repair_instructions must be empty unless verdict is repair_required",
                "repair_instructions must be non-empty when verdict is repair_required",
            ],
        },
        sort_keys=True,
    )


def _dependency_decision_repair_prompt(
    *,
    request: DependencyDecisionRequest,
    invalid_decision_text: str,
    validation_error: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Repair the invalid ATHBA dependency decision. Return raw JSON only.",
            "blocked_requirement_ref": request.step.requirement_refs[0],
            "planned_requirements": [item.to_dict() for item in request.contract.observable_requirements],
            "trusted_revision": request.trusted_revision,
            "mechanical_failure": request.evidence.to_dict(),
            "invalid_dependency_decision": invalid_decision_text,
            "validation_error": validation_error,
            "required_output": {
                "disposition": "already_planned|add_prerequisite|reject_dependency",
                "parent_requirement_ref": "string",
                "prerequisite_refs": ["string"],
                "prerequisite_observable": "string|null",
                "rationale": "string",
            },
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
            "repair_rules": [
                "retain the blocked requirement ref exactly",
                "choose exactly one bounded dependency disposition",
                "for already_planned, include one or more existing planned requirement refs and never use an empty prerequisite_refs list",
                "for add_prerequisite, add exactly one smallest observable prerequisite",
                "do not prescribe implementation steps, tests, or patches",
                "do not invent worker ids, model ids, GPU ids, endpoints, ports, or backend selection",
            ],
        },
        sort_keys=True,
    )


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
        validation_error: str | None = None
        try:
            return _semantic_review_from_response(
                request,
                result.text,
                label="semantic review",
            )
        except ValueError as error:
            if not _is_recoverable_semantic_review_error(error):
                raise
            validation_error = str(error)
        repaired = await self.gateway.reason(
            ReasoningRequest(
                purpose="athba_senior_review_repair",
                prompt=_semantic_review_repair_prompt(
                    request=request,
                    invalid_review_text=result.text,
                    validation_error=validation_error or "semantic review response was not valid JSON",
                ),
                project_id=request.contract.project_id,
                requires_large_context=True,
            )
        )
        return _semantic_review_from_response(
            request,
            repaired.text,
            label="semantic review repair",
        )


class ContractTestRuntime(Protocol):
    def red_command(self, test_name: str) -> list[str]: ...
    def test_command(self, target: str) -> list[str]: ...


def require_contract_runtime(runtime: ContractTestRuntime | None) -> ContractTestRuntime:
    if runtime is None:
        raise ValueError("contract work has no configured language runtime")
    return runtime


class ContractTesterWorkUnitFactory:
    def __init__(self, runtime: ContractTestRuntime | None = None):
        self.runtime = runtime

    def build(self, request: WorkUnitBuildRequest) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=red_work_unit_id(request.step.step_id),
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=_tester_objective(request.contract, request.step, request.repository_material),
            allowed_paths=[request.step.test_path],
            acceptance=AcceptanceContract(
                commands=[require_contract_runtime(self.runtime).red_command(request.step.test_name)],
                required_artifacts=[request.step.test_path],
            ),
            status=WorkUnitStatus.READY,
        )


class ContractDeveloperWorkUnitFactory:
    def __init__(self, runtime: ContractTestRuntime | None = None):
        self.runtime = runtime

    def build(self, request: WorkUnitBuildRequest) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=green_work_unit_id(request.step.step_id),
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=_developer_objective(request.contract, request.step, request.repository_material),
            allowed_paths=[request.step.production_path],
            acceptance=AcceptanceContract(
                commands=[require_contract_runtime(self.runtime).test_command(request.step.test_name), require_contract_runtime(self.runtime).test_command(request.step.test_path)],
                required_artifacts=[request.step.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


class ContractRepairWorkUnitFactory:
    def __init__(self, runtime: ContractTestRuntime | None = None):
        self.runtime = runtime

    def build(self, request: RepairWorkUnitBuildRequest) -> DevelopmentWorkUnit:
        attempt_number = request.cycle.repair_attempts + 1
        return DevelopmentWorkUnit(
            id=repair_work_unit_id(request.cycle.step.step_id, attempt_number),
            project_id=request.contract.project_id,
            parent_ticket_id=request.contract.id,
            objective=_repair_objective(request.contract, request.cycle.step, request.review),
            allowed_paths=[request.cycle.step.production_path],
            acceptance=AcceptanceContract(
                commands=[require_contract_runtime(self.runtime).test_command(request.cycle.step.test_name), require_contract_runtime(self.runtime).test_command(request.cycle.step.test_path)],
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
    red_acceptance_service: RedAcceptanceService | None = None
    runtime: ContractTestRuntime | None = None


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
    red_acceptance_service: RedAcceptanceService


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
        work_unit = _retry_scoped_work_unit(
            run_state.failure_progress,
            TddPhase.RED,
            dependencies.tester_factory.build(WorkUnitBuildRequest(contract, cycle.step, material)),
        )
        outcome = await dependencies.phase_executor.execute(
            PhaseExecutionRequest(
                TddPhase.RED,
                work_unit,
                run_state.repository_binding.with_base_sha(
                    cycle.base_revision or run_state.semantic_base_revision
                ),
            )
        )
        return await _advance_red_phase(run_state, cycle, contract, dependencies, work_unit, outcome)
    return await _advance_green_phase(run_state, cycle, contract, dependencies)


async def _advance_red_phase(
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    contract: BehaviorContract,
    dependencies: CycleProgressionDependencies,
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
        return await dependencies.failure_router.route(FailureRoutingRequest(run_state, TddPhase.RED, work_unit, outcome))
    analysis = await _assess_accepted_red(run_state, cycle, dependencies, outcome)
    updated_cycle = replace(cycle, red_phase=outcome.phase_state, red_analysis=analysis.analysis)
    if not analysis.is_valid_red:
        return await _route_rejected_red_analysis(run_state, contract, dependencies.failure_router, work_unit, outcome, updated_cycle, analysis)
    return RunAdvance(
        replace(
            run_state,
            cycles=_replace_current_cycle(run_state.cycles, updated_cycle),
            failure_progress=split_aware_success_state(run_state.failure_progress),
            blocked_reason=None,
        )
    )


async def _assess_accepted_red(
    run_state: BehaviorContractRunState,
    cycle: ContractCycleRecord,
    dependencies: CycleProgressionDependencies,
    outcome: PhaseOutcome,
) -> RedAcceptanceResult:
    accepted_revision = outcome.phase_state.accepted_revision
    evidence_location = outcome.phase_state.evidence_location
    repository_root = run_state.repository_binding.registered_root
    if accepted_revision is None:
        raise ValueError("accepted RED analysis requires an accepted revision")
    if repository_root is None:
        return fallback_red_acceptance_result(
            test_node=cycle.step.test_name,
            candidate_revision=accepted_revision,
            trusted_base_revision=run_state.semantic_base_revision,
            candidate_change_id=outcome.phase_state.change_id,
            evidence_location=evidence_location,
            rationale="legacy test fixture omitted external repository evidence; preserving prior accepted RED semantics for compatibility",
        )
    if evidence_location is None:
        return fail_closed_red_acceptance_result(
            test_node=cycle.step.test_name,
            candidate_revision=accepted_revision,
            trusted_base_revision=run_state.semantic_base_revision,
            candidate_change_id=outcome.phase_state.change_id,
            evidence_location=None,
            rationale="trusted RED evidence was missing for a registered external project",
        )
    try:
        return await dependencies.red_acceptance_service.evaluate(
            RedAcceptanceRequest(
                contract=run_state.contract,
                step=cycle.step,
                repository_root=repository_root,
                candidate_revision=accepted_revision,
                trusted_base_revision=run_state.semantic_base_revision,
                candidate_change_id=outcome.phase_state.change_id,
                evidence_location=evidence_location,
            )
        )
    except ValueError as error:
        return fail_closed_red_acceptance_result(
            test_node=cycle.step.test_name,
            candidate_revision=accepted_revision,
            trusted_base_revision=run_state.semantic_base_revision,
            candidate_change_id=outcome.phase_state.change_id,
            evidence_location=evidence_location,
            rationale=f"trusted RED evidence was unavailable or malformed for a registered external project: {error}",
        )


async def _route_rejected_red_analysis(
    run_state: BehaviorContractRunState,
    contract: BehaviorContract,
    failure_router: FailedCandidateRouter,
    work_unit: DevelopmentWorkUnit,
    outcome: PhaseOutcome,
    updated_cycle: ContractCycleRecord,
    analysis: RedAcceptanceResult,
) -> RunAdvance:
    routed_request = FailureRoutingRequest(
        replace(run_state, cycles=_replace_current_cycle(run_state.cycles, updated_cycle)),
        TddPhase.RED,
        work_unit,
        outcome,
    )
    transition = await _candidate_failure_transition_for_observation(
        failure_router.dependencies,
        routed_request,
        analysis.as_failure_observation(),
    )
    routed_state = failure_routing.apply_candidate_failure_transition(
        failure_routing.CandidateFailureTransitionRequest(
            run_state=routed_request.run_state,
            phase=TddPhase.RED,
            phase_state=outcome.phase_state,
        ),
        transition,
        failure_router.dependencies.failure_policy,
    )
    return RunAdvance(routed_state, return_now=transition.return_now)


async def _candidate_failure_transition_for_observation(
    dependencies: FailureRouterDependencies,
    request: FailureRoutingRequest,
    observation: FailureObservation,
) -> failure_routing.FailureTransition:
    cycle = request.run_state.current_cycle()
    if cycle is None:
        raise ValueError("failed candidate routing requires an active cycle")
    decision = dependencies.failure_policy.decide([observation])
    if decision.action is ProgressionAction.BLOCK_EXECUTOR:
        return failure_routing.transition_for_executor_block(decision, observation.message)
    if decision.action is ProgressionAction.RECOVER_ENVIRONMENT:
        recovered = await _environment_recovery_succeeded(dependencies, request.run_state, request.run_state.contract.project_id)
        return failure_routing.transition_for_environment(decision, observation.message, recovered)
    if decision.action is ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY:
        return await _mechanical_dependency_transition(dependencies, request, observation, decision, cycle)
    if decision.action in {ProgressionAction.REPAIR_CANDIDATE, ProgressionAction.REPAIR_TESTER, ProgressionAction.REPAIR_DEVELOPER, ProgressionAction.REPAIR_REGRESSION}:
        return _candidate_repair_transition(dependencies, request, observation, decision, cycle)
    if decision.action is ProgressionAction.SPLIT_PACKET:
        return await _split_transition(dependencies, request, observation, decision, cycle)
    if decision.action is ProgressionAction.REPLAN_DEPENDENCY:
        return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: {observation.message}")
    if decision.action is ProgressionAction.BLOCK_AMBIGUITY:
        return failure_routing.transition_for_block(decision, failure_routing.FailureRouteState.BLOCKED_AMBIGUITY, failure_routing.ContractPoolStatus.BLOCKED_AMBIGUITY, observation.message)
    if decision.action is ProgressionAction.REPLAN_INTEGRATION:
        return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: {observation.message}")
    if decision.action is ProgressionAction.BLOCK_ARCHITECTURE:
        return failure_routing.transition_for_block(decision, failure_routing.FailureRouteState.BLOCKED_ARCHITECTURE, failure_routing.ContractPoolStatus.BLOCKED_ARCHITECTURE, observation.message)
    if decision.action is ProgressionAction.ANALYZE_UNCLASSIFIED:
        return failure_routing.transition_for_block(decision, failure_routing.FailureRouteState.BLOCKED_UNCLASSIFIED, failure_routing.ContractPoolStatus.BLOCKED_UNCLASSIFIED, observation.message)
    return failure_routing.transition_for_replan(decision, f"{decision.dominant.value}: {observation.message}")


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
    work_unit = _retry_scoped_work_unit(
        run_state.failure_progress,
        TddPhase.GREEN,
        dependencies.developer_factory.build(WorkUnitBuildRequest(contract, cycle.step, material)),
    )
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


def _retry_scoped_work_unit(
    failure_progress: FailureProgressState,
    phase: TddPhase,
    work_unit: DevelopmentWorkUnit,
) -> DevelopmentWorkUnit:
    if failure_progress.state is not FailureRouteState.AWAITING_REPAIR:
        return work_unit
    if not failure_progress.repair_packets:
        return work_unit
    packet = failure_progress.repair_packets[-1]
    if packet.work_unit_id != work_unit.id:
        return work_unit
    retry_route = RetryRoute.TESTER_REPAIR if phase is TddPhase.RED else RetryRoute.DEVELOPER_REPAIR
    retry_count = failure_progress.retry_counts.get(retry_route.value, 0)
    if retry_count <= 0:
        return work_unit
    return replace(work_unit, change_key=f"{work_unit.id}--retry-{retry_count}")


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
        tester_factory = deps.tester_factory or ContractTesterWorkUnitFactory(deps.runtime)
        developer_factory = deps.developer_factory or ContractDeveloperWorkUnitFactory(deps.runtime)
        repair_factory = deps.repair_factory or ContractRepairWorkUnitFactory(deps.runtime)
        review_material_provider = deps.review_material_provider or _default_review_material_provider(deps.repository_binding)
        failure_policy = deps.failure_policy or FailureProgressionPolicy()
        dependency_planner = deps.dependency_planner or DependencyPrerequisitePlanner(deps.reasoning_gateway)
        self.run_store = ContractRunStore(state_repo)
        phase_executor = PhaseExecutor(deps.execution_gateway)
        split_planner = deps.split_planner or ResourceLimitSplitPlanner(deps.reasoning_gateway)
        policy_scope_resolver = deps.policy_scope_resolver or PolicyScopeViolationResolver()
        failure_router = FailedCandidateRouter(FailureRouterDependencies(failure_policy, deps.environment_recovery, dependency_planner, split_planner, repository_material_provider, deps.max_tester_repairs, deps.max_developer_repairs, policy_scope_resolver))
        red_acceptance_service = deps.red_acceptance_service or RedAcceptanceService(RedAcceptanceDependencies(verifier=RedBehaviorVerifier(deps.reasoning_gateway)))
        self.ready_progressor = ReadyPoolProgressor(ReadyPoolDependencies(step_planner, deps.gatekeeper, deps.gap_adapter, deps.repository_binding))
        self.cycle_progressor = CycleActiveProgressor(CycleProgressionDependencies(tester_factory, developer_factory, repository_material_provider, phase_executor, failure_router, red_acceptance_service))
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


def _decode_source_clauses(response: str) -> list[SourceRequirementClause]:
    payload = _json_object(response, label="source requirement clauses")
    raw_clauses = payload.get("clauses")
    if not isinstance(raw_clauses, list):
        raise ValueError("source requirement clauses response must include a clauses list")
    clauses: list[SourceRequirementClause] = []
    for raw_clause in raw_clauses:
        if not isinstance(raw_clause, dict):
            raise ValueError("source requirement clauses must be objects")
        payload_clause = dict(raw_clause)
        try:
            clauses.append(SourceRequirementClause.from_dict(payload_clause))
        except ValueError as error:
            ref = str(payload_clause.get("ref", "<unknown>"))
            field = _source_clause_error_field(str(error))
            raise ValueError(f"{error}: clause {ref} field {field}") from error
    if not clauses:
        raise ValueError("source requirement clauses must not be empty")
    refs = [clause.ref for clause in clauses]
    duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
    if duplicates:
        raise ValueError(f"duplicate source clause refs are not allowed: {duplicates}")
    return clauses


def _source_clause_error_field(error: str) -> str:
    if "evidence kind" in error:
        return "evidence_kind"
    if "kind" in error:
        return "kind"
    return "item"


def _source_clause_prompt(*, project_id: str, requirement_text: str) -> str:
    return json.dumps(
        {
            "instruction": "Produce ATHBA PR16 source requirement clauses as raw JSON only.",
            "output_rules": _source_clause_output_rules(),
            "project_id": project_id,
            "requirement_text": requirement_text,
            "required_json_schema": _source_clause_schema(),
            "rules": _source_clause_rules(),
        },
        indent=2,
        sort_keys=True,
    )


def _source_clause_repair_prompt(
    *,
    project_id: str,
    requirement_text: str,
    invalid_response: str,
    validation_error: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Repair the invalid ATHBA PR16 source requirement clauses. Return the complete corrected clauses as raw JSON only.",
            "output_rules": _source_clause_output_rules() + ["return the complete corrected clauses"],
            "project_id": project_id,
            "requirement_text": requirement_text,
            "invalid_source_clause_draft": invalid_response,
            "validation_error": validation_error,
            "required_json_schema": _source_clause_schema(),
            "rules": _source_clause_rules(),
            "repair_rules": [
                "correct every contract violation visible in the invalid draft, not only the single validation error reported",
                "keep kind separate from evidence_kind",
                "invariant is valid only as kind and must never be used as evidence_kind",
                "do not broaden enums, coerce invalid values, or invent requirements to satisfy validation",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _source_clause_targeted_repair_prompt(
    *,
    project_id: str,
    issue: _SourceClauseValidationIssue,
) -> str:
    if issue.raw_clause is None:
        raise ValueError("targeted source clause repair requires an offending clause")
    return json.dumps(
        {
            "instruction": "Repair only the identified ATHBA PR16 source requirement clause. Return exactly one corrected clause object as raw JSON only.",
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "return exactly one corrected clause object, not a clauses list or wrapper",
                "do not include ref or source_quote; ATHBA retains stable identity and source authority",
            ],
            "project_id": project_id,
            "stable_clause_location": issue.location,
            "offending_clause": issue.raw_clause,
            "retained_source_passage": issue.raw_clause["source_quote"],
            "validation_error": issue.message,
            "required_json_schema": _source_clause_targeted_repair_schema(),
            "rules": _source_clause_rules(),
            "repair_rules": [
                "correct only the reported validation error for this one clause",
                "preserve the clause's original meaning and source grounding",
                "do not invent requirements to satisfy validation",
            ],
        },
        indent=2,
        sort_keys=True,
    )

def _source_clause_split_prompt(
    *,
    project_id: str,
    requirement_text: str,
    offending_clause: dict[str, object],
    validation_error: str,
) -> str:
    return json.dumps(
        {
            "instruction": "Decompose only the offending source clause into smaller source-grounded clauses. Return raw JSON only.",
            "project_id": project_id,
            "requirement_text": requirement_text,
            "offending_source_passage": offending_clause.get("source_quote", ""),
            "offending_clause": offending_clause,
            "validation_error": validation_error,
            "required_json_schema": _source_clause_split_schema(),
            "rules": [
                "return either disposition split or not_produced",
                "a split must contain at least two smaller distinct children",
                "preserve the complete parent obligation without inventing behavior, errors, restrictions or capabilities",
                "preserve explicit error and state-preservation requirements in the children",
                "retain the parent source passage on every child",
                "do not assign child refs; ATHBA assigns deterministic refs",
                "not_produced must explain why meaningful decomposition is unavailable",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _source_clause_split_format_repair_prompt(
    *,
    request: _SourceClauseSplitRequest,
    invalid_response: str,
    validation_error: str,
) -> str:
    issue = request.issue
    return json.dumps(
        {
            "instruction": "Correct only the JSON/schema format of this source-clause split response. Return raw JSON only.",
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
            "project_id": request.project_id,
            "requirement_text": request.requirement_text,
            "offending_source_passage": (issue.raw_clause or {}).get("source_quote", ""),
            "offending_clause": issue.raw_clause or {},
            "source_clause_validation_error": issue.message,
            "invalid_split_response": invalid_response,
            "format_validation_error": validation_error,
            "required_json_schema": _source_clause_split_schema(),
            "format_repair_rules": [
                "this is format-only repair; do not semantically replan or decompose",
                "do not add, remove, merge, or change child obligations",
                "preserve the original disposition, child count, child fields, source grounding, and meanings",
                "do not assign child refs; ATHBA assigns deterministic refs",
            ],
        },
        indent=2,
        sort_keys=True,
    )

def _source_clause_targeted_repair_schema() -> dict[str, object]:
    return {
        "text": "string",
        "kind": "behavior|validation|invariant|constraint|quality",
        "evidence_kind": "test|mechanical|review",
        "subject": "a grounded source subject",
        "obligation_type": "observable_behavior|precondition|error_behavior|invariant|mechanical_assurance|non_persistence_assurance|naming",
    }


def _source_clause_split_schema() -> dict[str, object]:
    return {
        "disposition": "split|not_produced",
        "rationale": "string",
        "coverage_rationale": "string required for split",
        "children": [
            {
                "text": "string",
                "kind": "behavior|validation|invariant|constraint|quality",
                "evidence_kind": "test|mechanical|review",
                "source_quote": "the exact parent source passage",
                "subject": "a grounded source subject",
                "obligation_type": "optional classification",
            }
        ],
    }


def _source_clause_output_rules() -> list[str]:
    return [
        "return raw JSON only",
        "do not wrap the JSON in Markdown",
        "do not use code fences",
        "do not add commentary before or after the JSON",
        "include one top-level clauses array",
        "do not add extra fields outside the required schema",
    ]


def _source_clause_schema() -> dict[str, object]:
    return {
        "clauses": [
            {
                "ref": "string",
                "text": "string",
                "kind": "behavior|validation|invariant|constraint|quality",
                "evidence_kind": "test|mechanical|review",
                "source_quote": "exact original source passage",
                "subject": "one contiguous relevant subject from that passage",
                "obligation_type": "observable_behavior|precondition|error_behavior|invariant|mechanical_assurance|non_persistence_assurance|naming",
            }
        ]
    }


def _source_clause_rules() -> list[str]:
    return [
        "one source obligation per clause",
        "include source_quote and subject grounded in original text; classification is validated deterministically",
        "validation without explicit rejection/error is precondition: only valid-input behavior is specified; outside-domain behavior is unspecified",
        "do not invent runtime validation, rejection, exception type, coercion or out-of-domain behavior",
        "explicit rejection is error_behavior and gets a separate small observable obligation",
        "keep dependency assurance and non-persistence assurance in separate clauses",
        "do not bundle unrelated behaviors into one clause",
        "preserve happy-path, failure, query, and state-preservation obligations",
        "preserve constraint and quality obligations from the source text",
        "kind must be one of behavior, validation, invariant, constraint, quality",
        "evidence_kind must be one of test, mechanical, review",
        "invariant is a requirement kind and is not an evidence_kind",
        "use test for executable behavior and validation obligations by default",
        "use review for readability and unnecessary-abstraction obligations",
        "for quality clauses, evidence_kind must be review and must never be quality",
        "use mechanical for deterministic environment or dependency constraints",
        "do not include implementation details",
        "retain explicitly source-mandated public call signatures verbatim; parameters and their order are functional authority, not implementation choices",
        "do not invent requirements beyond reasonable decomposition of the supplied text",
        "keep the clause set complete enough that every meaningful behavioral obligation from the source text is represented",
        "do not include worker ids, model ids, GPU ids, endpoints, ports, or backend selection",
    ]


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
        "component_name": "string",
        "capability": "string",
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
            "required_signatures": [item.to_dict() for item in required_signatures(requirement_text)],
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
                "precondition clauses define valid inputs, not an independent rejection requirement; use valid examples and attach relevant domain source refs to the corresponding behavior",
                "outside-domain behavior is unspecified unless original source explicitly defines it; never invent ValueError or any other rejection",
                "error_expectation must be null and error_semantics empty unless source explicitly requires error behavior",
                "each observable_requirements entry must describe one independently verifiable behavior or invariant slice",
                "one requirement ref must be completable by one focused semantic TDD slice",
                "if two cases require distinct tests or distinct failure conditions, give them separate refs",
                "do not bundle unrelated failure modes under one requirement ref",
                "multiple observable requirements may reference the same source clause when that improves TDD granularity",
                "do not pre-author a future Tester step list",
                "declare depends_on only for a real prerequisite requirement in this contract; use an empty array when independently executable",
            ],
            "traceability_rules": [
                "every supplied source clause must be covered by its appropriate evidence channel; only evidence_kind=test clauses are required to appear in observable requirement source_refs",
                "every supplied source clause whose evidence_kind is test must be covered by at least one observable requirement source_refs entry",
                "each observable requirement must include at least one evidence_kind=test source ref; mechanical or review refs may be supplementary but must never be the sole source_refs",
                "copy source clause refs exactly into source_refs",
                "do not invent source refs",
                "do not leave an evidence_kind=test source clause represented only in invariants, completion_criteria, or error_semantics",
                "each observable requirement must include a non-empty source_refs array",
            ],
            "domain_rules": [
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
    project_id: str,
    requirement_text: str,
    source_clauses: list[SourceRequirementClause],
    allowed_production_paths: list[str],
    allowed_test_paths: list[str],
) -> BehaviorContract:
    payload = _json_object(text, label=label)
    payload["project_id"] = project_id
    payload["requirement_source"] = requirement_text
    payload["source_clauses"] = [clause.to_dict() for clause in source_clauses]
    payload["status"] = ContractPoolStatus.TDD_READY.value
    contract = BehaviorContract.from_dict(
        payload,
        BehaviorContractLoadOptions(
            allowed_production_paths=allowed_production_paths,
            allowed_test_paths=allowed_test_paths,
        ),
    )
    from core.development.source_obligation_semantics import validate_contract_authority
    validate_contract_authority(contract)
    return contract


def _is_recoverable_contract_error(error: ValueError) -> bool:
    message = str(error)
    return (
        message.startswith("test-evidence source clauses must be covered by observable requirements:")
        or message.startswith("observable requirements must include at least one test-evidence source clause:")
        or message.startswith("source does not specify rejection")
        or message.startswith("error identifier is not specified by source")
    )


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
                "component_name": "string",
                "capability": "string",
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
            },
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
            ],
            "repair_rules": [
                "precondition/domain constraints specify valid inputs only; remove invented out-of-domain behavior or exception types",
                "do not create a standalone observable requirement whose only authority is a precondition",
                "keep the contract within the supplied repository-relative production and test paths",
                "preserve valid semantic fields where possible",
                "every supplied source clause ref whose evidence_kind is test must appear in at least one observable_requirements[].source_refs entry",
                "each observable requirement must include at least one evidence_kind=test source ref; mechanical or review refs may be retained only as supplementary traceability",
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
        "Visible contract files are empty. Choose a bootstrap behavior that establishes the component or a minimal public API before downstream validations. "
        f"Use only repository-visible modules such as `{module_name}` and preserve inspectable failure evidence without encoding a specific import workaround. "
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
            "review_scope": _semantic_review_scope(
                SemanticReviewRequest(
                    contract,
                    run_state,
                    cycle,
                    candidate_revision,
                    review_material,
                )
            ),
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
                "review only the active step requirement refs plus already semantically approved requirement refs",
                "do not fail this candidate solely because other future contract requirements remain unimplemented",
                "if you cite contract source refs in evidence_refs, they must come only from review_scope.allowed_source_refs",
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
        "The proposed pytest node must be created exactly. Do not hide bootstrap or import preconditions with collection-workaround recipes; if the behavior cannot yet be exercised, keep the test descriptive and evidence-preserving. "
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


def _semantic_review_scope(request: SemanticReviewRequest) -> dict[str, object]:
    scoped_requirement_refs = [
        *request.run_state.completed_requirement_refs,
        *request.cycle.step.requirement_refs,
    ]
    return {
        "active_step_requirement_refs": list(request.cycle.step.requirement_refs),
        "approved_requirement_refs": list(request.run_state.completed_requirement_refs),
        "allowed_source_refs": _source_refs_for_requirements(
            request.contract,
            scoped_requirement_refs,
        ),
    }


def _source_refs_for_requirements(
    contract: BehaviorContract,
    requirement_refs: list[str],
) -> list[str]:
    allowed = set(requirement_refs)
    source_refs: list[str] = []
    for requirement in contract.observable_requirements:
        if requirement.ref not in allowed:
            continue
        for source_ref in requirement.source_refs:
            if source_ref not in source_refs:
                source_refs.append(source_ref)
    return source_refs


def _out_of_scope_review_source_refs(
    request: SemanticReviewRequest,
    review: SemanticReviewResult,
) -> list[str]:
    contract_source_refs = {clause.ref for clause in request.contract.source_clauses}
    allowed_source_refs = set(
        _source_refs_for_requirements(
            request.contract,
            [*request.run_state.completed_requirement_refs, *request.cycle.step.requirement_refs],
        )
    )
    out_of_scope = [
        ref
        for ref in review.evidence_refs
        if ref in contract_source_refs and ref not in allowed_source_refs
    ]
    return sorted(set(out_of_scope))


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
    item_kinds = {item.ref: item.kind for item in gatekeeper_state.checklist.items}
    for gap in gatekeeper_state.latest_assessment.gaps:
        if item_kinds.get(gap.checklist_ref) not in {"behavior", "validation", "invariant"}:
            continue
        try:
            matching_contract_source_refs_for_gap(contract, gap)
        except ValueError:
            continue
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
