"""Deterministic PR20 failure classification and recovery routing.

This module deliberately classifies development evidence, not defects in ATHBA
itself.  It has no Rack AI implementation knowledge: adapters translate their
structured result into :class:`FailureObservation` at the application edge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureClassification(str, Enum):
    EXECUTOR_INFRASTRUCTURE_FAILURE = "executor_infrastructure_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    RESOURCE_LIMIT_FAILURE = "resource_limit_failure"
    SYNTAX_OR_PARSE_FAILURE = "syntax_or_parse_failure"
    BUILD_OR_LINK_FAILURE = "build_or_link_failure"
    TEST_COLLECTION_OR_BOOTSTRAP_FAILURE = "test_collection_or_bootstrap_failure"
    SECURITY_OR_EXECUTION_POLICY_VIOLATION = "security_or_execution_policy_violation"
    CHANGE_SCOPE_VIOLATION = "change_scope_violation"
    DEPENDENCY_OR_PREREQUISITE_FAILURE = "dependency_or_prerequisite_failure"
    CONTRACT_OR_REQUIREMENT_AMBIGUITY = "contract_or_requirement_ambiguity"
    TESTER_CANDIDATE_DEFECT = "tester_candidate_defect"
    DEVELOPER_CANDIDATE_DEFECT = "developer_candidate_defect"
    EXPECTED_BEHAVIOR_RED = "expected_behavior_red"
    ACCUMULATED_REGRESSION = "accumulated_regression"
    SEMANTIC_INTEGRATION_FAILURE = "semantic_integration_failure"
    REVIEW_QUALITY_FAILURE = "review_quality_failure"
    ARCHITECTURE_CONSTRAINT_VIOLATION = "architecture_constraint_violation"
    UNCLASSIFIED_FAILURE = "unclassified_failure"


# The numeric ordering is the policy ordering, not an LLM judgement.
FAILURE_PRIORITY = {classification: index for index, classification in enumerate(FailureClassification, start=1)}


class ProgressionAction(str, Enum):
    BLOCK_EXECUTOR = "block_executor"
    RECOVER_ENVIRONMENT = "recover_environment"
    SPLIT_PACKET = "split_packet"
    ASSESS_MECHANICAL_DEPENDENCY = "assess_mechanical_dependency"
    REPAIR_TESTER = "repair_tester"
    REPAIR_DEVELOPER = "repair_developer"
    REPLAN_DEPENDENCY = "replan_dependency"
    BLOCK_AMBIGUITY = "block_ambiguity"
    ACCEPT_RED = "accept_red"
    REPAIR_REGRESSION = "repair_regression"
    REPLAN_INTEGRATION = "replan_integration"
    REPAIR_REVIEW = "repair_review"
    BLOCK_ARCHITECTURE = "block_architecture"
    ANALYZE_UNCLASSIFIED = "analyze_unclassified"


class FailureRouteState(str, Enum):
    ACTIVE = "active"
    AWAITING_REPAIR = "awaiting_repair"
    DEFERRED_DEPENDENCY = "deferred_dependency"
    AWAITING_PREREQUISITE = "awaiting_prerequisite"
    AWAITING_ENVIRONMENT_RECOVERY = "awaiting_environment_recovery"
    AWAITING_SPLIT = "awaiting_split"
    BLOCKED_EXECUTOR = "blocked_executor"
    BLOCKED_ARCHITECTURE = "blocked_architecture"
    BLOCKED_AMBIGUITY = "blocked_ambiguity"
    BLOCKED_UNCLASSIFIED = "blocked_unclassified"
    ACCEPTED_RED = "accepted_red"


class PacketKind(str, Enum):
    FRESH = "fresh"
    REPAIR = "repair"


class DependencyDisposition(str, Enum):
    ALREADY_PLANNED = "already_planned"
    ADD_PREREQUISITE = "add_prerequisite"
    REJECT_DEPENDENCY = "reject_dependency"


@dataclass(frozen=True)
class DependencyDecision:
    """Bounded Behavior-Planner decision; it does not prescribe an implementation."""

    disposition: DependencyDisposition
    parent_requirement_ref: str
    prerequisite_refs: list[str]
    rationale: str
    prerequisite_observable: str | None = None

    def __post_init__(self) -> None:
        if not self.parent_requirement_ref.strip() or not self.rationale.strip():
            raise ValueError("dependency decision parent requirement and rationale must be non-empty")
        if self.disposition is not DependencyDisposition.REJECT_DEPENDENCY and not self.prerequisite_refs:
            raise ValueError("accepted dependency decisions require prerequisites")
        if self.disposition is DependencyDisposition.ADD_PREREQUISITE and (self.prerequisite_observable is None or not self.prerequisite_observable.strip()):
            raise ValueError("a justified prerequisite requires an observable behavior")

    def to_dict(self) -> dict[str, Any]:
        return {"disposition": self.disposition.value, "parent_requirement_ref": self.parent_requirement_ref, "prerequisite_refs": list(self.prerequisite_refs), "rationale": self.rationale, "prerequisite_observable": self.prerequisite_observable}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DependencyDecision":
        return cls(DependencyDisposition(str(payload["disposition"])), str(payload["parent_requirement_ref"]), [str(item) for item in payload.get("prerequisite_refs", [])], str(payload["rationale"]), payload.get("prerequisite_observable"))


@dataclass(frozen=True)
class WorkPacketSplit:
    parent_work_unit_id: str
    child_work_unit_ids: list[str]
    preserved_objective: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.parent_work_unit_id.strip() or not self.preserved_objective.strip() or not self.rationale.strip():
            raise ValueError("split records require parent, objective, and rationale")
        if len(self.child_work_unit_ids) < 2 or len(set(self.child_work_unit_ids)) != len(self.child_work_unit_ids):
            raise ValueError("a split requires at least two unique child work units")

    def to_dict(self) -> dict[str, Any]:
        return {"parent_work_unit_id": self.parent_work_unit_id, "child_work_unit_ids": list(self.child_work_unit_ids), "preserved_objective": self.preserved_objective, "rationale": self.rationale}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkPacketSplit":
        return cls(str(payload["parent_work_unit_id"]), [str(item) for item in payload["child_work_unit_ids"]], str(payload["preserved_objective"]), str(payload["rationale"]))


@dataclass(frozen=True)
class UnclassifiedAnalysis:
    evidence_summary: str
    missing_category_description: str
    distinguishing_evidence: str

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.evidence_summary, self.missing_category_description, self.distinguishing_evidence)):
            raise ValueError("unclassified analysis fields must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_summary": self.evidence_summary, "missing_category_description": self.missing_category_description, "distinguishing_evidence": self.distinguishing_evidence}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnclassifiedAnalysis":
        return cls(str(payload["evidence_summary"]), str(payload["missing_category_description"]), str(payload["distinguishing_evidence"]))


@dataclass(frozen=True)
class FailureObservation:
    """Evidence observed for one unaccepted candidate or failed evaluation."""

    source: str
    message: str
    evidence_refs: list[str] = field(default_factory=list)
    plausible: list[FailureClassification] = field(default_factory=list)
    candidate_revision: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        if not self.source.strip() or not self.message.strip():
            raise ValueError("failure observation source and message must be non-empty")
        if len(set(self.plausible)) != len(self.plausible):
            raise ValueError("plausible classifications must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
            "plausible": [item.value for item in self.plausible],
            "candidate_revision": self.candidate_revision,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureObservation":
        return cls(
            source=str(payload["source"]),
            message=str(payload["message"]),
            evidence_refs=[str(item) for item in payload.get("evidence_refs", [])],
            plausible=[FailureClassification(str(item)) for item in payload.get("plausible", [])],
            candidate_revision=payload.get("candidate_revision"),
            stdout=payload.get("stdout"),
            stderr=payload.get("stderr"),
            status=payload.get("status"),
        )


@dataclass(frozen=True)
class FailureDecision:
    observations: list[FailureObservation]
    plausible: list[FailureClassification]
    dominant: FailureClassification
    priority: int
    action: ProgressionAction

    def to_dict(self) -> dict[str, Any]:
        return {
            "observations": [item.to_dict() for item in self.observations],
            "plausible": [item.value for item in self.plausible],
            "dominant": self.dominant.value,
            "priority": self.priority,
            "action": self.action.value,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureDecision":
        return cls(
            observations=[FailureObservation.from_dict(dict(item)) for item in payload["observations"]],
            plausible=[FailureClassification(str(item)) for item in payload["plausible"]],
            dominant=FailureClassification(str(payload["dominant"])),
            priority=int(payload["priority"]),
            action=ProgressionAction(str(payload["action"])),
        )


@dataclass(frozen=True)
class RepairPacket:
    """Role feedback, intentionally descriptive rather than prescriptive."""

    kind: PacketKind
    role: str
    work_unit_id: str
    trusted_revision: str | None
    original_objective: str
    allowed_paths: list[str]
    classification: FailureClassification | None = None
    previous_candidate: str | None = None
    evidence: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.role.strip() or not self.work_unit_id.strip() or not self.original_objective.strip():
            raise ValueError("repair packet role, work unit id, and objective must be non-empty")
        if not self.allowed_paths:
            raise ValueError("repair packet must preserve allowed paths")
        if self.kind is PacketKind.REPAIR and self.classification is None:
            raise ValueError("repair packets require a classification")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "role": self.role,
            "work_unit_id": self.work_unit_id,
            "trusted_revision": self.trusted_revision,
            "original_objective": self.original_objective,
            "allowed_paths": list(self.allowed_paths),
            "classification": None if self.classification is None else self.classification.value,
            "previous_candidate": self.previous_candidate,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RepairPacket":
        value = payload.get("classification")
        return cls(
            kind=PacketKind(str(payload["kind"])),
            role=str(payload["role"]),
            work_unit_id=str(payload["work_unit_id"]),
            trusted_revision=payload.get("trusted_revision"),
            original_objective=str(payload["original_objective"]),
            allowed_paths=[str(item) for item in payload["allowed_paths"]],
            classification=None if value is None else FailureClassification(str(value)),
            previous_candidate=payload.get("previous_candidate"),
            evidence=[str(item) for item in payload.get("evidence", [])],
        )


@dataclass(frozen=True)
class FailureProgressState:
    """Durable policy state attached to a behavior-contract run."""

    state: FailureRouteState = FailureRouteState.ACTIVE
    history: list[FailureDecision] = field(default_factory=list)
    retry_counts: dict[str, int] = field(default_factory=dict)
    deferred_requirement_refs: list[str] = field(default_factory=list)
    prerequisite_links: dict[str, list[str]] = field(default_factory=dict)
    split_children: dict[str, list[str]] = field(default_factory=dict)
    repair_packets: list[RepairPacket] = field(default_factory=list)
    dependency_decisions: list[DependencyDecision] = field(default_factory=list)
    splits: list[WorkPacketSplit] = field(default_factory=list)
    unclassified_analysis: UnclassifiedAnalysis | None = None
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "history": [item.to_dict() for item in self.history],
            "retry_counts": dict(self.retry_counts),
            "deferred_requirement_refs": list(self.deferred_requirement_refs),
            "prerequisite_links": {key: list(value) for key, value in self.prerequisite_links.items()},
            "split_children": {key: list(value) for key, value in self.split_children.items()},
            "repair_packets": [item.to_dict() for item in self.repair_packets],
            "dependency_decisions": [item.to_dict() for item in self.dependency_decisions],
            "splits": [item.to_dict() for item in self.splits],
            "unclassified_analysis": None if self.unclassified_analysis is None else self.unclassified_analysis.to_dict(),
            "blocker": self.blocker,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureProgressState":
        return cls(
            state=FailureRouteState(str(payload.get("state", FailureRouteState.ACTIVE.value))),
            history=[FailureDecision.from_dict(dict(item)) for item in payload.get("history", [])],
            retry_counts={str(key): int(value) for key, value in dict(payload.get("retry_counts", {})).items()},
            deferred_requirement_refs=[str(item) for item in payload.get("deferred_requirement_refs", [])],
            prerequisite_links={str(key): [str(item) for item in value] for key, value in dict(payload.get("prerequisite_links", {})).items()},
            split_children={str(key): [str(item) for item in value] for key, value in dict(payload.get("split_children", {})).items()},
            repair_packets=[RepairPacket.from_dict(dict(item)) for item in payload.get("repair_packets", [])],
            dependency_decisions=[DependencyDecision.from_dict(dict(item)) for item in payload.get("dependency_decisions", [])],
            splits=[WorkPacketSplit.from_dict(dict(item)) for item in payload.get("splits", [])],
            unclassified_analysis=None if payload.get("unclassified_analysis") is None else UnclassifiedAnalysis.from_dict(dict(payload["unclassified_analysis"])),
            blocker=payload.get("blocker"),
        )


class FailureProgressionPolicy:
    """Fixed priority and action table from PR20's source-controlled policy."""

    _ACTIONS = {
        FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE: ProgressionAction.BLOCK_EXECUTOR,
        FailureClassification.ENVIRONMENT_FAILURE: ProgressionAction.RECOVER_ENVIRONMENT,
        FailureClassification.RESOURCE_LIMIT_FAILURE: ProgressionAction.SPLIT_PACKET,
        FailureClassification.SYNTAX_OR_PARSE_FAILURE: ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY,
        FailureClassification.BUILD_OR_LINK_FAILURE: ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY,
        FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE: ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY,
        FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION: ProgressionAction.REPAIR_TESTER,
        FailureClassification.CHANGE_SCOPE_VIOLATION: ProgressionAction.REPAIR_TESTER,
        FailureClassification.DEPENDENCY_OR_PREREQUISITE_FAILURE: ProgressionAction.REPLAN_DEPENDENCY,
        FailureClassification.CONTRACT_OR_REQUIREMENT_AMBIGUITY: ProgressionAction.BLOCK_AMBIGUITY,
        FailureClassification.TESTER_CANDIDATE_DEFECT: ProgressionAction.REPAIR_TESTER,
        FailureClassification.DEVELOPER_CANDIDATE_DEFECT: ProgressionAction.REPAIR_DEVELOPER,
        FailureClassification.EXPECTED_BEHAVIOR_RED: ProgressionAction.ACCEPT_RED,
        FailureClassification.ACCUMULATED_REGRESSION: ProgressionAction.REPAIR_REGRESSION,
        FailureClassification.SEMANTIC_INTEGRATION_FAILURE: ProgressionAction.REPLAN_INTEGRATION,
        FailureClassification.REVIEW_QUALITY_FAILURE: ProgressionAction.REPAIR_REVIEW,
        FailureClassification.ARCHITECTURE_CONSTRAINT_VIOLATION: ProgressionAction.BLOCK_ARCHITECTURE,
        FailureClassification.UNCLASSIFIED_FAILURE: ProgressionAction.ANALYZE_UNCLASSIFIED,
    }

    def decide(self, observations: list[FailureObservation]) -> FailureDecision:
        if not observations:
            raise ValueError("at least one failure observation is required")
        plausible = sorted({item for observation in observations for item in observation.plausible}, key=FAILURE_PRIORITY.__getitem__)
        dominant = plausible[0] if plausible else FailureClassification.UNCLASSIFIED_FAILURE
        if not plausible:
            plausible = [dominant]
        return FailureDecision(
            observations=list(observations),
            plausible=plausible,
            dominant=dominant,
            priority=FAILURE_PRIORITY[dominant],
            action=self._ACTIONS[dominant],
        )

    def retry_allowed(self, state: FailureProgressState, route: str, *, budget: int) -> bool:
        if budget < 0:
            raise ValueError("retry budget cannot be negative")
        return state.retry_counts.get(route, 0) < budget

    def record(self, state: FailureProgressState, decision: FailureDecision, *, route: str | None = None, packet: RepairPacket | None = None, next_state: FailureRouteState | None = None, blocker: str | None = None) -> FailureProgressState:
        retries = dict(state.retry_counts)
        if route is not None:
            retries[route] = retries.get(route, 0) + 1
        return FailureProgressState(
            state=next_state or state.state,
            history=[*state.history, decision],
            retry_counts=retries,
            deferred_requirement_refs=list(state.deferred_requirement_refs),
            prerequisite_links={key: list(value) for key, value in state.prerequisite_links.items()},
            split_children={key: list(value) for key, value in state.split_children.items()},
            repair_packets=[*state.repair_packets, *([] if packet is None else [packet])],
            dependency_decisions=list(state.dependency_decisions),
            splits=list(state.splits),
            unclassified_analysis=state.unclassified_analysis,
            blocker=blocker if blocker is not None else state.blocker,
        )

    def defer_for_prerequisites(
        self,
        state: FailureProgressState,
        decision: FailureDecision,
        *,
        requirement_ref: str,
        prerequisite_refs: list[str],
    ) -> FailureProgressState:
        if not prerequisite_refs:
            raise ValueError("dependency deferral requires at least one prerequisite")
        recorded = self.record(state, decision, next_state=FailureRouteState.DEFERRED_DEPENDENCY)
        links = {key: list(value) for key, value in recorded.prerequisite_links.items()}
        links[requirement_ref] = list(prerequisite_refs)
        return FailureProgressState(
            state=FailureRouteState.DEFERRED_DEPENDENCY,
            history=recorded.history,
            retry_counts=recorded.retry_counts,
            deferred_requirement_refs=[*dict.fromkeys([*recorded.deferred_requirement_refs, requirement_ref])],
            prerequisite_links=links,
            split_children=recorded.split_children,
            repair_packets=recorded.repair_packets,
            dependency_decisions=[
                *recorded.dependency_decisions,
                DependencyDecision(DependencyDisposition.ALREADY_PLANNED, requirement_ref, list(prerequisite_refs), "Declared Behavior Contract prerequisites are not semantically approved."),
            ],
            splits=recorded.splits,
            unclassified_analysis=recorded.unclassified_analysis,
            blocker=recorded.blocker,
        )
