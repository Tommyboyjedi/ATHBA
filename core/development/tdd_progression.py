"""State records for ATHBA's RED/GREEN TDD coordinators."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from core.development.progression import ExecutionAttemptRecord
from core.execution.rack_ai_contract import RepositoryBinding


class TddPhase(str, Enum):
    RED = "red"
    GREEN = "green"
    COMPLETE = "complete"


CONTRACT_POOL_STATUSES = {
    "tdd_ready",
    "cycle_active",
    "review_ready",
    "repair_ready",
    "replan_ready",
    "approved",
    "completed",
}
REVIEW_VERDICTS = {"approved", "repair_required", "replan_required"}
STEP_DECISION_STATUSES = {"propose", "complete"}
CHECKLIST_ITEM_KINDS = {"behavior", "validation", "invariant", "constraint", "quality"}
CHECKLIST_EVIDENCE_KINDS = {"test", "mechanical", "review"}
CHECKLIST_ASSESSMENT_STATUSES = {"proven", "missing_test_evidence", "uncertain"}
GATEKEEPER_ASSESSMENT_STATUSES = {"complete", "incomplete"}


@dataclass(frozen=True)
class TddBehavior:
    id: str
    project_id: str
    parent_ticket_id: str
    description: str
    test_name: str
    test_path: str
    production_path: str
    red_objective: str
    green_objective: str
    red_acceptance_commands: list[list[str]]
    green_acceptance_commands: list[list[str]]

    def __post_init__(self) -> None:
        _require_text(self.id, "behavior id")
        _require_text(self.project_id, "project id")
        _require_text(self.parent_ticket_id, "parent ticket id")
        _require_text(self.description, "behavior description")
        _require_text(self.test_name, "test name")
        _require_text(self.test_path, "test path")
        _require_text(self.production_path, "production path")
        _require_text(self.red_objective, "red objective")
        _require_text(self.green_objective, "green objective")
        _validate_commands(self.red_acceptance_commands, "red acceptance commands")
        _validate_commands(self.green_acceptance_commands, "green acceptance commands")


@dataclass(frozen=True)
class TddPhaseState:
    phase: str
    work_unit_id: str
    base_sha: str | None = None
    status: str = "pending"
    accepted_revision: str | None = None
    evidence_location: str | None = None
    change_id: str | None = None
    branch: str | None = None
    worktree_path: str | None = None
    selected_worker_id: str | None = None
    error: str | None = None
    recorded_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "work_unit_id": self.work_unit_id,
            "base_sha": self.base_sha,
            "status": self.status,
            "accepted_revision": self.accepted_revision,
            "evidence_location": self.evidence_location,
            "change_id": self.change_id,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "selected_worker_id": self.selected_worker_id,
            "error": self.error,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddPhaseState":
        return cls(
            phase=str(payload["phase"]),
            work_unit_id=str(payload["work_unit_id"]),
            base_sha=payload.get("base_sha"),
            status=str(payload["status"]),
            accepted_revision=payload.get("accepted_revision"),
            evidence_location=payload.get("evidence_location"),
            change_id=payload.get("change_id"),
            branch=payload.get("branch"),
            worktree_path=payload.get("worktree_path"),
            selected_worker_id=payload.get("selected_worker_id"),
            error=payload.get("error"),
            recorded_at=payload.get("recorded_at"),
        )


@dataclass(frozen=True)
class TddBehaviorProgress:
    behavior_id: str
    description: str
    current_phase: str
    status: str
    red_phase: TddPhaseState
    green_phase: TddPhaseState

    @classmethod
    def from_behavior(cls, behavior: TddBehavior) -> "TddBehaviorProgress":
        return cls(
            behavior_id=behavior.id,
            description=behavior.description,
            current_phase=TddPhase.RED.value,
            status="pending",
            red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=red_work_unit_id(behavior.id)),
            green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=green_work_unit_id(behavior.id)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "behavior_id": self.behavior_id,
            "description": self.description,
            "current_phase": self.current_phase,
            "status": self.status,
            "red_phase": self.red_phase.to_dict(),
            "green_phase": self.green_phase.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TddBehaviorProgress":
        return cls(
            behavior_id=str(payload["behavior_id"]),
            description=str(payload["description"]),
            current_phase=str(payload["current_phase"]),
            status=str(payload["status"]),
            red_phase=TddPhaseState.from_dict(dict(payload["red_phase"])),
            green_phase=TddPhaseState.from_dict(dict(payload["green_phase"])),
        )


@dataclass(frozen=True)
class SourceRequirementClause:
    ref: str
    text: str
    kind: str
    evidence_kind: str = "test"

    def __post_init__(self) -> None:
        _require_text(self.ref, "source clause ref")
        _require_text(self.text, "source clause text")
        _require_text(self.kind, "source clause kind")
        if self.kind not in CHECKLIST_ITEM_KINDS:
            raise ValueError(f"unsupported source clause kind: {self.kind}")
        if self.evidence_kind not in CHECKLIST_EVIDENCE_KINDS:
            raise ValueError(f"unsupported source clause evidence kind: {self.evidence_kind}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "text": self.text,
            "kind": self.kind,
            "evidence_kind": self.evidence_kind,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SourceRequirementClause":
        kind = str(payload["kind"])
        return cls(
            ref=str(payload["ref"]),
            text=str(payload["text"]),
            kind=kind,
            evidence_kind=_normalize_evidence_kind(kind, payload.get("evidence_kind")),
        )


@dataclass(frozen=True)
class SpecificationChecklist:
    project_id: str
    requirement_text: str
    items: list[SourceRequirementClause]

    def __post_init__(self) -> None:
        _require_text(self.project_id, "checklist project id")
        _require_text(self.requirement_text, "checklist requirement text")
        if not self.items:
            raise ValueError("specification checklist items must not be empty")
        _validate_unique_refs([item.ref for item in self.items], "checklist item refs")

    def item_refs(self) -> list[str]:
        return [item.ref for item in self.items]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "requirement_text": self.requirement_text,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpecificationChecklist":
        items = payload.get("items")
        if not isinstance(items, list):
            raise ValueError("specification checklist items must be a list")
        return cls(
            project_id=str(payload["project_id"]),
            requirement_text=str(payload["requirement_text"]),
            items=[SourceRequirementClause.from_dict(dict(item)) for item in items],
        )


@dataclass(frozen=True)
class ChecklistEvidence:
    checklist_ref: str
    evidence_kind: str
    test_name: str | None = None
    test_path: str | None = None
    step_id: str | None = None
    requirement_ref: str | None = None
    accepted_revision: str | None = None
    semantic_revision: str | None = None
    evidence_location: str | None = None
    rationale: str | None = None
    status: str = "accepted"

    def __post_init__(self) -> None:
        _require_text(self.checklist_ref, "checklist evidence ref")
        if self.evidence_kind not in CHECKLIST_EVIDENCE_KINDS:
            raise ValueError(f"unsupported checklist evidence kind: {self.evidence_kind}")
        _require_text(self.status, "checklist evidence status")
        if self.test_name is not None:
            _require_text(self.test_name, "checklist evidence test name")
        if self.test_path is not None:
            _require_text(self.test_path, "checklist evidence test path")
        if self.step_id is not None:
            _require_text(self.step_id, "checklist evidence step id")
        if self.requirement_ref is not None:
            _require_text(self.requirement_ref, "checklist evidence requirement ref")
        if self.accepted_revision is not None:
            _require_text(self.accepted_revision, "checklist evidence accepted revision")
        if self.semantic_revision is not None:
            _require_text(self.semantic_revision, "checklist evidence semantic revision")
        if self.evidence_location is not None:
            _require_text(self.evidence_location, "checklist evidence location")
        if self.rationale is not None:
            _require_text(self.rationale, "checklist evidence rationale")
        if self.evidence_kind == "test":
            if self.test_name is None or self.test_path is None or self.step_id is None or self.semantic_revision is None:
                raise ValueError("test checklist evidence requires a test name, test path, step id, and semantic revision")

    def to_dict(self) -> dict[str, Any]:
        return {
            "checklist_ref": self.checklist_ref,
            "evidence_kind": self.evidence_kind,
            "test_name": self.test_name,
            "test_path": self.test_path,
            "step_id": self.step_id,
            "requirement_ref": self.requirement_ref,
            "accepted_revision": self.accepted_revision,
            "semantic_revision": self.semantic_revision,
            "evidence_location": self.evidence_location,
            "rationale": self.rationale,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChecklistEvidence":
        return cls(
            checklist_ref=str(payload["checklist_ref"]),
            evidence_kind=str(payload["evidence_kind"]),
            test_name=payload.get("test_name"),
            test_path=payload.get("test_path"),
            step_id=payload.get("step_id"),
            requirement_ref=payload.get("requirement_ref"),
            accepted_revision=payload.get("accepted_revision"),
            semantic_revision=payload.get("semantic_revision"),
            evidence_location=payload.get("evidence_location"),
            rationale=payload.get("rationale"),
            status=str(payload.get("status", "accepted")),
        )


@dataclass(frozen=True)
class SpecificationGap:
    checklist_ref: str
    obligation_text: str
    item_kind: str
    reason: str
    desired_proof: str
    related_test_names: list[str] = field(default_factory=list)
    status: str = "open"

    def __post_init__(self) -> None:
        _require_text(self.checklist_ref, "specification gap checklist ref")
        _require_text(self.obligation_text, "specification gap obligation text")
        if self.item_kind not in CHECKLIST_ITEM_KINDS:
            raise ValueError(f"unsupported specification gap item kind: {self.item_kind}")
        _require_text(self.reason, "specification gap reason")
        _require_text(self.desired_proof, "specification gap desired proof")
        _validate_list_of_strings(self.related_test_names, "specification gap related test names")
        _require_text(self.status, "specification gap status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "checklist_ref": self.checklist_ref,
            "obligation_text": self.obligation_text,
            "item_kind": self.item_kind,
            "reason": self.reason,
            "desired_proof": self.desired_proof,
            "related_test_names": list(self.related_test_names),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpecificationGap":
        return cls(
            checklist_ref=str(payload["checklist_ref"]),
            obligation_text=str(payload["obligation_text"]),
            item_kind=str(payload["item_kind"]),
            reason=str(payload["reason"]),
            desired_proof=str(payload["desired_proof"]),
            related_test_names=_list_of_strings(payload.get("related_test_names", []), "specification gap related test names"),
            status=str(payload.get("status", "open")),
        )


@dataclass(frozen=True)
class ChecklistItemAssessment:
    checklist_ref: str
    status: str
    rationale: str
    evidence: list[ChecklistEvidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_text(self.checklist_ref, "checklist assessment ref")
        if self.status not in CHECKLIST_ASSESSMENT_STATUSES:
            raise ValueError(f"unsupported checklist assessment status: {self.status}")
        _require_text(self.rationale, "checklist assessment rationale")
        if self.status == "proven" and not self.evidence:
            raise ValueError("proven checklist items require evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "checklist_ref": self.checklist_ref,
            "status": self.status,
            "rationale": self.rationale,
            "evidence": [item.to_dict() for item in self.evidence],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ChecklistItemAssessment":
        evidence = payload.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError("checklist assessment evidence must be a list")
        return cls(
            checklist_ref=str(payload["checklist_ref"]),
            status=str(payload["status"]),
            rationale=str(payload["rationale"]),
            evidence=[ChecklistEvidence.from_dict(dict(item)) for item in evidence],
        )


@dataclass(frozen=True)
class GatekeeperAssessmentRecord:
    status: str
    item_assessments: list[ChecklistItemAssessment]
    gaps: list[SpecificationGap] = field(default_factory=list)
    assessed_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in GATEKEEPER_ASSESSMENT_STATUSES:
            raise ValueError(f"unsupported gatekeeper assessment status: {self.status}")
        if not self.item_assessments:
            raise ValueError("gatekeeper item assessments must not be empty")
        _validate_unique_refs([item.checklist_ref for item in self.item_assessments], "gatekeeper assessment refs")
        if self.assessed_at is not None:
            _require_text(self.assessed_at, "gatekeeper assessed at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "item_assessments": [item.to_dict() for item in self.item_assessments],
            "gaps": [item.to_dict() for item in self.gaps],
            "assessed_at": self.assessed_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GatekeeperAssessmentRecord":
        item_assessments = payload.get("item_assessments")
        if not isinstance(item_assessments, list):
            raise ValueError("gatekeeper item assessments must be a list")
        gaps = payload.get("gaps", [])
        if not isinstance(gaps, list):
            raise ValueError("gatekeeper gaps must be a list")
        return cls(
            status=str(payload["status"]),
            item_assessments=[ChecklistItemAssessment.from_dict(dict(item)) for item in item_assessments],
            gaps=[SpecificationGap.from_dict(dict(item)) for item in gaps],
            assessed_at=payload.get("assessed_at"),
        )


@dataclass(frozen=True)
class SpecificationGatekeeperRunState:
    checklist: SpecificationChecklist
    latest_assessment: GatekeeperAssessmentRecord | None = None
    assessment_history: list[GatekeeperAssessmentRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.latest_assessment is not None and not self.assessment_history:
            raise ValueError("gatekeeper assessment history must include the latest assessment")

    def is_complete(self) -> bool:
        return self.latest_assessment is not None and self.latest_assessment.status == "complete"

    def unresolved_item_refs(self) -> list[str]:
        if self.latest_assessment is None:
            return self.checklist.item_refs()
        return [item.checklist_ref for item in self.latest_assessment.item_assessments if item.status != "proven"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "checklist": self.checklist.to_dict(),
            "latest_assessment": None if self.latest_assessment is None else self.latest_assessment.to_dict(),
            "assessment_history": [item.to_dict() for item in self.assessment_history],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpecificationGatekeeperRunState":
        latest_assessment = payload.get("latest_assessment")
        history = payload.get("assessment_history", [])
        if not isinstance(history, list):
            raise ValueError("gatekeeper assessment history must be a list")
        return cls(
            checklist=SpecificationChecklist.from_dict(dict(payload["checklist"])),
            latest_assessment=None if latest_assessment is None else GatekeeperAssessmentRecord.from_dict(dict(latest_assessment)),
            assessment_history=[GatekeeperAssessmentRecord.from_dict(dict(item)) for item in history],
        )


@dataclass(frozen=True)
class BehaviorContractRequirement:
    ref: str
    source_refs: list[str]
    summary: str
    observable_outcome: str
    test_hint: str
    error_expectation: str | None = None
    preserves_state_on_failure: bool = True

    def __post_init__(self) -> None:
        _require_text(self.ref, "requirement ref")
        if not self.source_refs:
            raise ValueError("requirement source refs must not be empty")
        _validate_list_of_strings(self.source_refs, "requirement source refs")
        _require_text(self.summary, "requirement summary")
        _require_text(self.observable_outcome, "requirement observable outcome")
        _require_text(self.test_hint, "requirement test hint")
        if self.error_expectation is not None:
            _require_text(self.error_expectation, "requirement error expectation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "source_refs": list(self.source_refs),
            "summary": self.summary,
            "observable_outcome": self.observable_outcome,
            "test_hint": self.test_hint,
            "error_expectation": self.error_expectation,
            "preserves_state_on_failure": self.preserves_state_on_failure,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BehaviorContractRequirement":
        return cls(
            ref=str(payload["ref"]),
            source_refs=_list_of_strings(payload.get("source_refs"), "requirement source refs"),
            summary=str(payload["summary"]),
            observable_outcome=str(payload["observable_outcome"]),
            test_hint=str(payload["test_hint"]),
            error_expectation=payload.get("error_expectation"),
            preserves_state_on_failure=bool(payload.get("preserves_state_on_failure", True)),
        )


@dataclass(frozen=True)
class BehaviorContract:
    id: str
    project_id: str
    component_name: str
    capability: str
    requirement_source: str
    source_clauses: list[SourceRequirementClause]
    observable_requirements: list[BehaviorContractRequirement]
    invariants: list[str]
    production_paths: list[str]
    test_paths: list[str]
    public_api: list[str] = field(default_factory=list)
    error_semantics: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    status: str = "tdd_ready"

    def __post_init__(self) -> None:
        _require_text(self.id, "contract id")
        _require_text(self.project_id, "project id")
        _require_text(self.component_name, "component name")
        _require_text(self.capability, "component capability")
        _require_text(self.requirement_source, "requirement source")
        if not self.source_clauses:
            raise ValueError("source clauses must not be empty")
        if not self.observable_requirements:
            raise ValueError("observable requirements must not be empty")
        _validate_unique_refs(self.source_clause_refs(), "source clause refs")
        _validate_unique_refs(self.requirement_refs(), "requirement refs")
        _validate_contract_source_coverage(self)
        _validate_list_of_strings(self.invariants, "invariants")
        _validate_repository_relative_paths(self.production_paths, "production paths")
        _validate_repository_relative_paths(self.test_paths, "test paths")
        _validate_list_of_strings(self.public_api, "public api")
        _validate_list_of_strings(self.error_semantics, "error semantics")
        _validate_list_of_strings(self.non_goals, "non-goals")
        _validate_list_of_strings(self.completion_criteria, "completion criteria")
        if self.status not in CONTRACT_POOL_STATUSES:
            raise ValueError(f"unsupported contract status: {self.status}")

    def source_clause_refs(self) -> list[str]:
        return [clause.ref for clause in self.source_clauses]

    def requirement_refs(self) -> list[str]:
        return [requirement.ref for requirement in self.observable_requirements]

    def uncovered_requirement_refs(self, completed_refs: list[str]) -> list[str]:
        completed = set(completed_refs)
        return [ref for ref in self.requirement_refs() if ref not in completed]

    def uncovered_source_clause_refs(self) -> list[str]:
        covered = {ref for requirement in self.observable_requirements for ref in requirement.source_refs}
        return [ref for ref in self.source_clause_refs() if ref not in covered]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "component_name": self.component_name,
            "capability": self.capability,
            "requirement_source": self.requirement_source,
            "source_clauses": [item.to_dict() for item in self.source_clauses],
            "observable_requirements": [item.to_dict() for item in self.observable_requirements],
            "invariants": list(self.invariants),
            "production_paths": list(self.production_paths),
            "test_paths": list(self.test_paths),
            "public_api": list(self.public_api),
            "error_semantics": list(self.error_semantics),
            "non_goals": list(self.non_goals),
            "completion_criteria": list(self.completion_criteria),
            "status": self.status,
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        allowed_production_paths: list[str] | None = None,
        allowed_test_paths: list[str] | None = None,
    ) -> "BehaviorContract":
        source_clauses = payload.get("source_clauses")
        if not isinstance(source_clauses, list):
            raise ValueError("source_clauses must be a list")
        requirements = payload.get("observable_requirements")
        if not isinstance(requirements, list):
            raise ValueError("observable_requirements must be a list")
        contract = cls(
            id=str(payload["id"]),
            project_id=str(payload["project_id"]),
            component_name=str(payload["component_name"]),
            capability=str(payload["capability"]),
            requirement_source=str(payload["requirement_source"]),
            source_clauses=[SourceRequirementClause.from_dict(dict(item)) for item in source_clauses],
            observable_requirements=[BehaviorContractRequirement.from_dict(dict(item)) for item in requirements],
            invariants=_list_of_strings(payload.get("invariants"), "invariants"),
            production_paths=_list_of_strings(payload.get("production_paths"), "production_paths"),
            test_paths=_list_of_strings(payload.get("test_paths"), "test_paths"),
            public_api=_list_of_strings(payload.get("public_api", []), "public api"),
            error_semantics=_list_of_strings(payload.get("error_semantics", []), "error semantics"),
            non_goals=_list_of_strings(payload.get("non_goals", []), "non-goals"),
            completion_criteria=_list_of_strings(payload.get("completion_criteria", []), "completion criteria"),
            status=str(payload.get("status", "tdd_ready")),
        )
        _validate_allowed_path_subset(contract.production_paths, allowed_production_paths, "production paths")
        _validate_allowed_path_subset(contract.test_paths, allowed_test_paths, "test paths")
        return contract


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
        _require_text(self.step_id, "step id")
        if not self.requirement_refs:
            raise ValueError("requirement refs must not be empty")
        _validate_list_of_strings(self.requirement_refs, "requirement refs")
        _require_text(self.focused_behavior, "focused behavior")
        _require_text(self.test_name, "test name")
        _require_text(self.expected_result, "expected result")
        _require_text(self.test_path, "test path")
        _require_text(self.production_path, "production path")
        _require_text(self.red_objective, "red objective")
        _require_text(self.green_objective, "green objective")
        _require_text(self.reason_next_smallest, "reason next smallest")
        if self.exception_type is not None:
            _require_text(self.exception_type, "exception type")
        if self.exception_message is not None:
            _require_text(self.exception_message, "exception message")

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
            requirement_refs=_list_of_strings(payload.get("requirement_refs"), "requirement refs"),
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
        if self.status not in STEP_DECISION_STATUSES:
            raise ValueError(f"unsupported step decision status: {self.status}")
        _require_text(self.rationale, "step decision rationale")
        _validate_list_of_strings(self.completed_requirement_refs, "completed requirement refs")
        if self.status == "propose" and self.proposal is None:
            raise ValueError("propose decisions require a proposal")
        if self.status == "complete" and self.proposal is not None:
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
            completed_requirement_refs=_list_of_strings(payload.get("completed_requirement_refs", []), "completed requirement refs"),
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
        if self.verdict not in REVIEW_VERDICTS:
            raise ValueError(f"unsupported semantic review verdict: {self.verdict}")
        _require_text(self.rationale, "review rationale")
        _require_text(self.candidate_revision, "candidate revision")
        _require_text(self.step_id, "review step id")
        _validate_list_of_strings(self.findings, "review findings")
        _validate_list_of_strings(self.evidence_refs, "review evidence refs")
        _validate_list_of_strings(self.repair_instructions, "repair instructions")
        if self.verdict == "repair_required" and not self.repair_instructions:
            raise ValueError("repair_required review results must include repair instructions")
        if self.verdict == "approved" and self.repair_instructions:
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
            findings=_list_of_strings(payload.get("findings", []), "review findings"),
            candidate_revision=str(payload["candidate_revision"]),
            step_id=str(payload["step_id"]),
            evidence_refs=_list_of_strings(payload.get("evidence_refs", []), "review evidence refs"),
            repair_instructions=_list_of_strings(payload.get("repair_instructions", []), "repair instructions"),
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
    repair_attempts: int = 0

    def __post_init__(self) -> None:
        if self.pool not in CONTRACT_POOL_STATUSES:
            raise ValueError(f"unsupported cycle pool: {self.pool}")
        if self.repair_attempts < 0:
            raise ValueError("repair attempts must not be negative")

    @classmethod
    def from_step(cls, step: TddStepProposal, *, base_revision: str | None) -> "ContractCycleRecord":
        return cls(
            step=step,
            pool="cycle_active",
            base_revision=base_revision,
            red_phase=TddPhaseState(phase=TddPhase.RED.value, work_unit_id=red_work_unit_id(step.step_id)),
            green_phase=TddPhaseState(phase=TddPhase.GREEN.value, work_unit_id=green_work_unit_id(step.step_id)),
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
            "repair_attempts": self.repair_attempts,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ContractCycleRecord":
        red_phase = payload.get("red_phase")
        green_phase = payload.get("green_phase")
        review_result = payload.get("review_result")
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
            repair_attempts=int(payload.get("repair_attempts", 0)),
        )


@dataclass(frozen=True)
class BehaviorContractRunState:
    contract: BehaviorContract
    repository_binding: RepositoryBinding
    semantic_base_revision: str | None
    current_pool: str = "tdd_ready"
    completed_requirement_refs: list[str] = field(default_factory=list)
    cycles: list[ContractCycleRecord] = field(default_factory=list)
    blocked_reason: str | None = None
    gatekeeper_state: SpecificationGatekeeperRunState | None = None
    targeted_requirement_ref: str | None = None
    targeted_checklist_ref: str | None = None

    def __post_init__(self) -> None:
        if self.current_pool not in CONTRACT_POOL_STATUSES:
            raise ValueError(f"unsupported contract run pool: {self.current_pool}")
        _validate_list_of_strings(self.completed_requirement_refs, "completed requirement refs")
        unknown = set(self.completed_requirement_refs) - set(self.contract.requirement_refs())
        if unknown:
            raise ValueError(f"completed requirement refs not in contract: {sorted(unknown)}")
        if self.targeted_requirement_ref is not None:
            _require_text(self.targeted_requirement_ref, "targeted requirement ref")
            if self.targeted_requirement_ref not in self.contract.requirement_refs():
                raise ValueError("targeted requirement ref must be in contract")
        if self.targeted_checklist_ref is not None:
            _require_text(self.targeted_checklist_ref, "targeted checklist ref")
        if self.blocked_reason is not None:
            _require_text(self.blocked_reason, "blocked reason")
        if self.gatekeeper_state is not None and self.gatekeeper_state.checklist.project_id != self.contract.project_id:
            raise ValueError("gatekeeper checklist project id must match the contract project id")

    def active_requirement_refs(self) -> list[str]:
        if self.targeted_requirement_ref is not None:
            return [self.targeted_requirement_ref]
        return self.contract.requirement_refs()

    def current_cycle(self) -> ContractCycleRecord | None:
        return self.cycles[-1] if self.cycles else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract.to_dict(),
            "repository_binding": {
                "repository_id": self.repository_binding.repository_id,
                "base_ref": self.repository_binding.base_ref,
                "base_sha": self.repository_binding.base_sha,
                "registered_root": self.repository_binding.registered_root,
            },
            "semantic_base_revision": self.semantic_base_revision,
            "current_pool": self.current_pool,
            "completed_requirement_refs": list(self.completed_requirement_refs),
            "cycles": [cycle.to_dict() for cycle in self.cycles],
            "blocked_reason": self.blocked_reason,
            "gatekeeper_state": None if self.gatekeeper_state is None else self.gatekeeper_state.to_dict(),
            "targeted_requirement_ref": self.targeted_requirement_ref,
            "targeted_checklist_ref": self.targeted_checklist_ref,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BehaviorContractRunState":
        binding = payload["repository_binding"]
        return cls(
            contract=BehaviorContract.from_dict(dict(payload["contract"])),
            repository_binding=RepositoryBinding(
                repository_id=str(binding["repository_id"]),
                base_ref=str(binding["base_ref"]),
                base_sha=binding.get("base_sha"),
                registered_root=binding.get("registered_root"),
            ),
            semantic_base_revision=payload.get("semantic_base_revision"),
            current_pool=str(payload.get("current_pool", "tdd_ready")),
            completed_requirement_refs=_list_of_strings(payload.get("completed_requirement_refs", []), "completed requirement refs"),
            cycles=[ContractCycleRecord.from_dict(dict(item)) for item in payload.get("cycles", [])],
            blocked_reason=payload.get("blocked_reason"),
            gatekeeper_state=None if payload.get("gatekeeper_state") is None else SpecificationGatekeeperRunState.from_dict(dict(payload["gatekeeper_state"])),
            targeted_requirement_ref=payload.get("targeted_requirement_ref"),
            targeted_checklist_ref=payload.get("targeted_checklist_ref"),
        )


@dataclass(frozen=True)
class TddSnapshot:
    project_id: str
    repository_binding: RepositoryBinding
    current_trusted_revision: str | None
    completed_behavior_ids: list[str] = field(default_factory=list)
    attempts: list[ExecutionAttemptRecord] = field(default_factory=list)
    behaviors: dict[str, TddBehaviorProgress] = field(default_factory=dict)
    blocked_behavior_id: str | None = None
    blocked_phase: str | None = None
    blocked_reason: str | None = None
    contract_runs: dict[str, BehaviorContractRunState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "repository_binding": {
                "repository_id": self.repository_binding.repository_id,
                "base_ref": self.repository_binding.base_ref,
                "base_sha": self.repository_binding.base_sha,
                "registered_root": self.repository_binding.registered_root,
            },
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
        binding = payload["repository_binding"]
        return cls(
            project_id=str(payload["project_id"]),
            repository_binding=RepositoryBinding(
                repository_id=str(binding["repository_id"]),
                base_ref=str(binding["base_ref"]),
                base_sha=binding.get("base_sha"),
                registered_root=binding.get("registered_root"),
            ),
            current_trusted_revision=payload.get("current_trusted_revision"),
            completed_behavior_ids=[str(item) for item in payload.get("completed_behavior_ids", [])],
            attempts=[ExecutionAttemptRecord.from_dict(item) for item in payload.get("attempts", [])],
            behaviors={
                str(key): TddBehaviorProgress.from_dict(value)
                for key, value in payload.get("behaviors", {}).items()
            },
            blocked_behavior_id=payload.get("blocked_behavior_id"),
            blocked_phase=payload.get("blocked_phase"),
            blocked_reason=payload.get("blocked_reason"),
            contract_runs={
                str(key): BehaviorContractRunState.from_dict(value)
                for key, value in payload.get("contract_runs", {}).items()
            },
        )


def red_work_unit_id(behavior_id: str) -> str:
    _require_text(behavior_id, "behavior id")
    return f"{behavior_id}--red"


def green_work_unit_id(behavior_id: str) -> str:
    _require_text(behavior_id, "behavior id")
    return f"{behavior_id}--green"


def repair_work_unit_id(step_id: str, attempt_number: int) -> str:
    _require_text(step_id, "step id")
    if attempt_number <= 0:
        raise ValueError("attempt number must be positive")
    return f"{step_id}--repair-{attempt_number}"


def _validate_commands(commands: list[list[str]], label: str) -> None:
    if not commands:
        raise ValueError(f"{label} must not be empty")
    for command in commands:
        if not command:
            raise ValueError(f"{label} must not contain empty commands")
        if any(not isinstance(arg, str) or not arg for arg in command):
            raise ValueError(f"{label} must contain non-empty string arguments")


def _validate_list_of_strings(values: list[str], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")


def _list_of_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    result = [str(item) for item in value]
    _validate_list_of_strings(result, label)
    return result


def _validate_repository_relative_paths(values: list[str], label: str) -> None:
    _validate_list_of_strings(values, label)
    for value in values:
        _validate_repository_relative_path(value, label)


def _validate_allowed_path_subset(values: list[str], allowed: list[str] | None, label: str) -> None:
    if allowed is None or not allowed:
        return
    disallowed = [value for value in values if value not in allowed]
    if disallowed:
        raise ValueError(f"{label} must be selected from the allowed path set")


def _validate_unique_refs(refs: list[str], label: str) -> None:
    duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label} are not allowed: {duplicates}")


def _validate_contract_source_coverage(contract: BehaviorContract) -> None:
    clause_refs = contract.source_clause_refs()
    clause_ref_set = set(clause_refs)
    seen_source_refs: set[str] = set()
    for requirement in contract.observable_requirements:
        for source_ref in requirement.source_refs:
            if source_ref not in clause_ref_set:
                raise ValueError(f"requirement source refs must exist in source clauses: {source_ref}")
            seen_source_refs.add(source_ref)
    uncovered = [ref for ref in clause_refs if ref not in seen_source_refs]
    if uncovered:
        raise ValueError(f"source clauses must be covered by observable requirements: {uncovered}")


def _default_evidence_kind(kind: str) -> str:
    if kind == "quality":
        return "review"
    if kind == "constraint":
        return "mechanical"
    return "test"


def _normalize_evidence_kind(kind: str, value: object) -> str:
    if value is None:
        return _default_evidence_kind(kind)
    normalized = str(value).strip()
    if not normalized:
        return _default_evidence_kind(kind)
    if normalized == "quality":
        return "review"
    return normalized


def _validate_repository_relative_path(value: str, label: str) -> None:
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} must contain repository-relative paths")
    if "/" not in candidate.as_posix() and "." not in candidate.name:
        raise ValueError(f"{label} must contain repository-relative file paths")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
