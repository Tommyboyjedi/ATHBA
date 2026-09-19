from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.development.behavior_contract_domain import BehaviorContract
from core.development.failure_state import FailureProgressState, validate_failure_progress_state
from core.development.red_acceptance import RedCandidateAnalysis
from core.development.progression import ExecutionAttemptRecord
from core.development.specification_domain import SpecificationGatekeeperRunState
from core.development.tdd_domain import TddPhaseState, green_work_unit_id, red_work_unit_id
from core.development.tdd_progression_validation import (
    enum_value,
    list_of_strings,
    require_text,
    validate_list_of_strings,
)
from core.development.tdd_progression_values import ContractPoolStatus, ReviewVerdict, StepDecisionStatus
from core.execution.rack_ai_contract import RepositoryBinding


@dataclass(frozen=True)
class TddStepProposal:
    step_id: str
    requirement_refs: list[str]
    focused_behavior: str
    test_name: str
    expected_result: str
    test_path: str
    production_path: str
    red_objective: str
    green_objective: str
    reason_next_smallest: str
    exception_type: str | None = None
    exception_message: str | None = None

    def __post_init__(self) -> None:
        require_text(self.step_id, "step id")
        if not self.requirement_refs:
            raise ValueError("requirement refs must not be empty")
        validate_list_of_strings(self.requirement_refs, "requirement refs")
        require_text(self.focused_behavior, "focused behavior")
        require_text(self.test_name, "test name")
        require_text(self.expected_result, "expected result")
        require_text(self.test_path, "test path")
        require_text(self.production_path, "production path")
        require_text(self.red_objective, "red objective")
        require_text(self.green_objective, "green objective")
        require_text(self.reason_next_smallest, "reason next smallest")
        if self.exception_type is not None:
            require_text(self.exception_type, "exception type")
        if self.exception_message is not None:
            require_text(self.exception_message, "exception message")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "requirement_refs": list(self.requirement_refs),
            "focused_behavior": self.focused_behavior,
            "test_name": self.test_name,
            "expected_result": self.expected_result,
            "test_path": self.test_path,
            "production_path": self.production_path,
            "red_objective": self.red_objective,
            "green_objective": self.green_objective,
            "reason_next_smallest": self.reason_next_smallest,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddStepProposal":
        return cls(
            step_id=str(payload["step_id"]),
            requirement_refs=list_of_strings(payload.get("requirement_refs"), "requirement refs"),
            focused_behavior=str(payload["focused_behavior"]),
            test_name=str(payload["test_name"]),
            expected_result=str(payload["expected_result"]),
            test_path=str(payload["test_path"]),
            production_path=str(payload["production_path"]),
            red_objective=str(payload["red_objective"]),
            green_objective=str(payload["green_objective"]),
            reason_next_smallest=str(payload["reason_next_smallest"]),
            exception_type=payload.get("exception_type"),
            exception_message=payload.get("exception_message"),
        )


@dataclass(frozen=True)
class TddStepDecision:
    status: str
    rationale: str
    proposal: TddStepProposal | None = None
    completed_requirement_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", enum_value(self.status, StepDecisionStatus, "step decision status"))
        require_text(self.rationale, "step decision rationale")
        validate_list_of_strings(self.completed_requirement_refs, "completed requirement refs")
        if self.status == StepDecisionStatus.PROPOSE.value and self.proposal is None:
            raise ValueError("propose decisions require a proposal")
        if self.status == StepDecisionStatus.COMPLETE.value and self.proposal is not None:
            raise ValueError("complete decisions must not include a proposal")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rationale": self.rationale,
            "proposal": self.proposal.to_dict() if self.proposal is not None else None,
            "completed_requirement_refs": list(self.completed_requirement_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddStepDecision":
        proposal_payload = payload.get("proposal")
        proposal = None if proposal_payload is None else TddStepProposal.from_dict(dict(proposal_payload))
        return cls(
            status=str(payload["status"]),
            rationale=str(payload["rationale"]),
            proposal=proposal,
            completed_requirement_refs=list_of_strings(payload.get("completed_requirement_refs", []), "completed requirement refs"),
        )


@dataclass(frozen=True)
class SemanticReviewResult:
    verdict: str
    rationale: str
    findings: list[str]
    candidate_revision: str
    step_id: str
    evidence_refs: list[str] = field(default_factory=list)
    repair_instructions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", enum_value(self.verdict, ReviewVerdict, "semantic review verdict"))
        require_text(self.rationale, "review rationale")
        require_text(self.candidate_revision, "candidate revision")
        require_text(self.step_id, "review step id")
        validate_list_of_strings(self.findings, "review findings")
        validate_list_of_strings(self.evidence_refs, "review evidence refs")
        validate_list_of_strings(self.repair_instructions, "repair instructions")
        if self.verdict == ReviewVerdict.REPAIR_REQUIRED.value and not self.repair_instructions:
            raise ValueError("repair_required review results must include repair instructions")
        if self.verdict == ReviewVerdict.APPROVED.value and self.repair_instructions:
            raise ValueError("approved review results must not include repair instructions")

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "rationale": self.rationale,
            "findings": list(self.findings),
            "candidate_revision": self.candidate_revision,
            "step_id": self.step_id,
            "evidence_refs": list(self.evidence_refs),
            "repair_instructions": list(self.repair_instructions),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticReviewResult":
        return cls(
            verdict=str(payload["verdict"]),
            rationale=str(payload["rationale"]),
            findings=list_of_strings(payload.get("findings", []), "review findings"),
            candidate_revision=str(payload["candidate_revision"]),
            step_id=str(payload["step_id"]),
            evidence_refs=list_of_strings(payload.get("evidence_refs", []), "review evidence refs"),
            repair_instructions=list_of_strings(payload.get("repair_instructions", []), "repair instructions"),
        )


@dataclass(frozen=True)
class ContractCycleRecord:
    step: TddStepProposal
    pool: str
    base_revision: str | None = None
    red_phase: TddPhaseState | None = None
    green_phase: TddPhaseState | None = None
    candidate_revision: str | None = None
    semantic_revision: str | None = None
    review_result: SemanticReviewResult | None = None
    review_history: list[SemanticReviewResult] = field(default_factory=list)
    red_analysis: RedCandidateAnalysis | None = None
    repair_attempts: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "pool", enum_value(self.pool, ContractPoolStatus, "cycle pool"))
        if self.repair_attempts < 0:
            raise ValueError("repair attempts must not be negative")

    @classmethod
    def from_step(cls, step: TddStepProposal, base_revision: str | None) -> "ContractCycleRecord":
        return cls(
            step=step,
            pool=ContractPoolStatus.CYCLE_ACTIVE.value,
            base_revision=base_revision,
            red_phase=TddPhaseState(phase="red", work_unit_id=red_work_unit_id(step.step_id)),
            green_phase=TddPhaseState(phase="green", work_unit_id=green_work_unit_id(step.step_id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step.to_dict(),
            "pool": self.pool,
            "base_revision": self.base_revision,
            "red_phase": None if self.red_phase is None else self.red_phase.to_dict(),
            "green_phase": None if self.green_phase is None else self.green_phase.to_dict(),
            "candidate_revision": self.candidate_revision,
            "semantic_revision": self.semantic_revision,
            "review_result": None if self.review_result is None else self.review_result.to_dict(),
            "review_history": [item.to_dict() for item in self.review_history],
            "red_analysis": None if self.red_analysis is None else self.red_analysis.to_dict(),
            "repair_attempts": self.repair_attempts,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContractCycleRecord":
        red_phase = payload.get("red_phase")
        green_phase = payload.get("green_phase")
        review_result = payload.get("review_result")
        red_analysis = payload.get("red_analysis")
        return cls(
            step=TddStepProposal.from_dict(dict(payload["step"])),
            pool=str(payload["pool"]),
            base_revision=payload.get("base_revision"),
            red_phase=None if red_phase is None else TddPhaseState.from_dict(dict(red_phase)),
            green_phase=None if green_phase is None else TddPhaseState.from_dict(dict(green_phase)),
            candidate_revision=payload.get("candidate_revision"),
            semantic_revision=payload.get("semantic_revision"),
            review_result=None if review_result is None else SemanticReviewResult.from_dict(dict(review_result)),
            review_history=[SemanticReviewResult.from_dict(dict(item)) for item in payload.get("review_history", [])],
            red_analysis=None if red_analysis is None else RedCandidateAnalysis.from_dict(dict(red_analysis)),
            repair_attempts=int(payload.get("repair_attempts", 0)),
        )


@dataclass(frozen=True)
class BehaviorContractRunState:
    contract: BehaviorContract
    repository_binding: RepositoryBinding
    semantic_base_revision: str | None
    current_pool: str = ContractPoolStatus.TDD_READY.value
    completed_requirement_refs: list[str] = field(default_factory=list)
    cycles: list[ContractCycleRecord] = field(default_factory=list)
    blocked_reason: str | None = None
    gatekeeper_state: SpecificationGatekeeperRunState | None = None
    targeted_requirement_ref: str | None = None
    targeted_checklist_ref: str | None = None
    failure_progress: FailureProgressState = field(default_factory=FailureProgressState)

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_pool", enum_value(self.current_pool, ContractPoolStatus, "contract run pool"))
        validate_list_of_strings(self.completed_requirement_refs, "completed requirement refs")
        unknown = set(self.completed_requirement_refs) - set(self.contract.requirement_refs())
        if unknown:
            raise ValueError(f"completed requirement refs not in contract: {sorted(unknown)}")
        if self.targeted_requirement_ref is not None:
            require_text(self.targeted_requirement_ref, "targeted requirement ref")
            if self.targeted_requirement_ref not in self.contract.requirement_refs():
                raise ValueError("targeted requirement ref must be in contract")
        if self.targeted_checklist_ref is not None:
            require_text(self.targeted_checklist_ref, "targeted checklist ref")
        if self.blocked_reason is not None:
            require_text(self.blocked_reason, "blocked reason")
        if self.gatekeeper_state is not None and self.gatekeeper_state.checklist.project_id != self.contract.project_id:
            raise ValueError("gatekeeper checklist project id must match the contract project id")
        validate_failure_progress_state(self.current_pool, self.failure_progress, self.blocked_reason)

    def active_requirement_refs(self) -> list[str]:
        if self.targeted_requirement_ref is not None:
            return [self.targeted_requirement_ref]
        return self.contract.requirement_refs()

    def current_cycle(self) -> ContractCycleRecord | None:
        return self.cycles[-1] if self.cycles else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_dict(),
            "repository_binding": self.repository_binding.to_dict(),
            "semantic_base_revision": self.semantic_base_revision,
            "current_pool": self.current_pool,
            "completed_requirement_refs": list(self.completed_requirement_refs),
            "cycles": [cycle.to_dict() for cycle in self.cycles],
            "blocked_reason": self.blocked_reason,
            "gatekeeper_state": None if self.gatekeeper_state is None else self.gatekeeper_state.to_dict(),
            "targeted_requirement_ref": self.targeted_requirement_ref,
            "targeted_checklist_ref": self.targeted_checklist_ref,
            "failure_progress": self.failure_progress.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BehaviorContractRunState":
        return cls(
            contract=BehaviorContract.from_dict(dict(payload["contract"])),
            repository_binding=RepositoryBinding.from_dict(dict(payload["repository_binding"])),
            semantic_base_revision=payload.get("semantic_base_revision"),
            current_pool=str(payload.get("current_pool", ContractPoolStatus.TDD_READY.value)),
            completed_requirement_refs=list_of_strings(payload.get("completed_requirement_refs", []), "completed requirement refs"),
            cycles=[ContractCycleRecord.from_dict(dict(item)) for item in payload.get("cycles", [])],
            blocked_reason=payload.get("blocked_reason"),
            gatekeeper_state=None if payload.get("gatekeeper_state") is None else SpecificationGatekeeperRunState.from_dict(dict(payload["gatekeeper_state"])),
            targeted_requirement_ref=payload.get("targeted_requirement_ref"),
            targeted_checklist_ref=payload.get("targeted_checklist_ref"),
            failure_progress=FailureProgressState.from_dict(dict(payload.get("failure_progress", {}))),
        )


@dataclass(frozen=True)
class TddSnapshot:
    project_id: str
    repository_binding: RepositoryBinding
    current_trusted_revision: str | None
    completed_behavior_ids: list[str] = field(default_factory=list)
    attempts: list[ExecutionAttemptRecord] = field(default_factory=list)
    behaviors: dict[str, Any] = field(default_factory=dict)
    blocked_behavior_id: str | None = None
    blocked_phase: str | None = None
    blocked_reason: str | None = None
    contract_runs: dict[str, BehaviorContractRunState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_text(self.project_id, "snapshot project id")
        validate_list_of_strings(self.completed_behavior_ids, "completed behavior ids")
        if self.blocked_behavior_id is not None:
            require_text(self.blocked_behavior_id, "blocked behavior id")
        if self.blocked_phase is not None:
            require_text(self.blocked_phase, "blocked phase")
        if self.blocked_reason is not None:
            require_text(self.blocked_reason, "blocked reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "repository_binding": self.repository_binding.to_dict(),
            "current_trusted_revision": self.current_trusted_revision,
            "completed_behavior_ids": list(self.completed_behavior_ids),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "behaviors": {key: value.to_dict() for key, value in sorted(self.behaviors.items())},
            "blocked_behavior_id": self.blocked_behavior_id,
            "blocked_phase": self.blocked_phase,
            "blocked_reason": self.blocked_reason,
            "contract_runs": {key: value.to_dict() for key, value in sorted(self.contract_runs.items())},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddSnapshot":
        from core.development.tdd_domain import TddBehaviorProgress

        return cls(
            project_id=str(payload["project_id"]),
            repository_binding=RepositoryBinding.from_dict(dict(payload["repository_binding"])),
            current_trusted_revision=payload.get("current_trusted_revision"),
            completed_behavior_ids=[str(item) for item in payload.get("completed_behavior_ids", [])],
            attempts=[ExecutionAttemptRecord.from_dict(item) for item in payload.get("attempts", [])],
            behaviors={str(key): TddBehaviorProgress.from_dict(value) for key, value in payload.get("behaviors", {}).items()},
            blocked_behavior_id=payload.get("blocked_behavior_id"),
            blocked_phase=payload.get("blocked_phase"),
            blocked_reason=payload.get("blocked_reason"),
            contract_runs={str(key): BehaviorContractRunState.from_dict(value) for key, value in payload.get("contract_runs", {}).items()},
        )
