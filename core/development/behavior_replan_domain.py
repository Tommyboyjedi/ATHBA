"""Parent-only decomposition authority and durable recovery evidence."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from core.development.behavior_contract_domain import BehaviorContractRequirement
from core.development.specification_domain import SourceRequirementClause


class BehaviorReplanDisposition(str, Enum):
    SPLIT = "split"
    NOT_PRODUCED = "not_produced"
    SOURCE_AUTHORITY_INSUFFICIENT = "source_authority_insufficient"


class BehaviorReplanPhase(str, Enum):
    REQUIRED = "behavior_replan_required"
    STARTED = "behavior_replan_started"
    RECEIVED = "behavior_split_received"
    CORRECTION_STARTED = "behavior_replan_correction_started"
    SUPERSEDED = "behavior_split"
    FAILED = "behavior_replan_failed"


class BehaviorReplanBlocker(str, Enum):
    NOT_PRODUCED = "behavior_atomisation_not_produced"
    BUDGET_EXHAUSTED = "behavior_atomisation_budget_exhausted"
    SOURCE_AUTHORITY_INSUFFICIENT = "behavior_source_authority_insufficient"
    INVALID_SPLIT = "behavior_replan_invalid_split"
    PROTOCOL_FAILURE = "behavior_replan_protocol_failure"
    PROVIDER_FAILURE = "behavior_replan_provider_failure"
    INTERRUPTED = "behavior_replan_interrupted"


@dataclass(frozen=True)
class BehaviorReplanPolicy:
    # A total tree budget bounds breadth as well as recursive depth.
    max_splits: int = 256
    max_children_per_split: int = 32

    def __post_init__(self) -> None:
        if type(self.max_splits) is not int or type(self.max_children_per_split) is not int or self.max_splits < 1 or self.max_children_per_split < 2:
            raise ValueError("replan safety budgets must permit decomposition")


@dataclass(frozen=True)
class BehavioralFailure:
    """Concise semantic evidence; transcripts and execution internals remain in their stores."""
    behavior_ref: str
    summary: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.behavior_ref.strip() or not self.summary.strip():
            raise ValueError("behavioral failure requires an obligation and a diagnosis")


@dataclass(frozen=True)
class BehaviorReplanRequest:
    project_id: str
    parent: BehaviorContractRequirement
    source_clauses: tuple[SourceRequirementClause, ...]
    canonical_ref: str
    canonical_revision: str
    failure_summary: str
    failure_evidence: tuple[str, ...] = ()
    lineage: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(not value.strip() for value in (self.project_id, self.canonical_ref,
                                               self.canonical_revision, self.failure_summary)):
            raise ValueError("replan requires trusted identity and semantic failure evidence")
        if {item.ref for item in self.source_clauses} != set(self.parent.source_refs):
            raise ValueError("replan source clauses must cover precisely the parent refs")
        if self.parent.ref in self.lineage or len(set(self.lineage)) != len(self.lineage):
            raise ValueError("replan lineage contains a cycle")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "behavior-atomisation/v2",
            "project_id": self.project_id, "parent": self.parent.to_dict(),
            "source_clauses": [item.to_dict() for item in self.source_clauses],
            "canonical_ref": self.canonical_ref, "canonical_revision": self.canonical_revision,
            "failure_summary": self.failure_summary, "failure_evidence": list(self.failure_evidence),
            "lineage": list(self.lineage),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BehaviorReplanRequest:
        if value.get("schema") != "behavior-atomisation/v2":
            raise ValueError("legacy semantic recovery state requires explicit migration")
        return cls(
            value["project_id"], BehaviorContractRequirement.from_dict(value["parent"]),
            tuple(SourceRequirementClause.from_dict(item) for item in value["source_clauses"]),
            value["canonical_ref"], value["canonical_revision"], value["failure_summary"],
            tuple(value["failure_evidence"]), tuple(value["lineage"]),
        )


@dataclass(frozen=True)
class BehaviorReplanCorrectionRequest:
    request: BehaviorReplanRequest
    rejected_response: str
    validation_error: str
    format_only: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.rejected_response, str) or not self.validation_error.strip():
            raise ValueError("replan correction requires rejected response and validation error")


@dataclass(frozen=True)
class BehaviorReplanResponse:
    disposition: BehaviorReplanDisposition
    rationale: str
    children: tuple[BehaviorContractRequirement, ...] = ()
    narrowing_rationales: tuple[str, ...] = ()
    coverage_rationale: str = ""
    raw_response: str = ""

    def __post_init__(self) -> None:
        if not self.rationale.strip():
            raise ValueError("replanning requires a rationale")
        if self.disposition != BehaviorReplanDisposition.SPLIT:
            if self.children or self.narrowing_rationales:
                raise ValueError("a no-split response cannot contain children")
        elif (len(self.children) < 2 or len(self.narrowing_rationales) != len(self.children)
              or not all(item.strip() for item in self.narrowing_rationales)
              or not self.coverage_rationale.strip()):
            raise ValueError("split requires at least two children, narrowing and coverage rationales")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value, "rationale": self.rationale,
            "children": [item.to_dict() for item in self.children],
            "narrowing_rationales": list(self.narrowing_rationales),
            "coverage_rationale": self.coverage_rationale, "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BehaviorReplanResponse:
        return cls(
            BehaviorReplanDisposition(value["disposition"]), value["rationale"],
            tuple(BehaviorContractRequirement.from_dict(item) for item in value["children"]),
            tuple(value["narrowing_rationales"]), value["coverage_rationale"], value["raw_response"],
        )


@dataclass(frozen=True)
class BehaviorReplanRecord:
    request: BehaviorReplanRequest
    phase: BehaviorReplanPhase = BehaviorReplanPhase.REQUIRED
    response: BehaviorReplanResponse | None = None
    blocker: BehaviorReplanBlocker | None = None
    detail: str | None = None
    rejected_response: str | None = None
    structure_digest: str | None = None
    correction_attempted: bool = False
    validation_errors: tuple[str, ...] = ()
    rejected_responses: tuple[str, ...] = ()

    @property
    def child_refs(self) -> tuple[str, ...]:
        return () if self.response is None else tuple(item.ref for item in self.response.children)

    @property
    def split_depth(self) -> int:
        return len(self.request.lineage)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(), "phase": self.phase.value,
            "response": None if self.response is None else self.response.to_dict(),
            "blocker": None if self.blocker is None else self.blocker.value,
            "detail": self.detail, "rejected_response": self.rejected_response,
            "structure_digest": self.structure_digest,
            "correction_attempted": self.correction_attempted,
            "validation_errors": list(self.validation_errors),
            "rejected_responses": list(self.rejected_responses),
            "parent_behavior_ref": self.request.parent.ref,
            "child_behavior_refs": list(self.child_refs), "split_depth": self.split_depth,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> BehaviorReplanRecord:
        record = cls(
            BehaviorReplanRequest.from_dict(value["request"]), BehaviorReplanPhase(value["phase"]),
            None if value["response"] is None else BehaviorReplanResponse.from_dict(value["response"]),
            None if value["blocker"] is None else BehaviorReplanBlocker(value["blocker"]),
            value["detail"], value["rejected_response"], value["structure_digest"],
            bool(value.get("correction_attempted", False)),
            tuple(str(item) for item in value.get("validation_errors", ())),
            tuple(str(item) for item in value.get("rejected_responses", ())),
        )
        if (value["parent_behavior_ref"] != record.request.parent.ref
                or tuple(value["child_behavior_refs"]) != record.child_refs
                or value["split_depth"] != record.split_depth):
            raise ValueError("corrupt behavior split lineage")
        return record
