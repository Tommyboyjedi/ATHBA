from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.development.failure_values import (
    DependencyDisposition,
    FailureClassification,
    PacketKind,
    ProgressionAction,
)


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")


def _string_list(values: list[str], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")


@dataclass(frozen=True)
class DependencyDecision:
    """Bounded Behavior-Planner decision; it does not prescribe an implementation."""

    disposition: DependencyDisposition
    parent_requirement_ref: str
    prerequisite_refs: list[str]
    rationale: str
    prerequisite_observable: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.parent_requirement_ref, "dependency decision parent requirement")
        _require_text(self.rationale, "dependency decision rationale")
        _string_list(self.prerequisite_refs, "dependency prerequisite refs")
        if self.disposition is not DependencyDisposition.REJECT_DEPENDENCY and not self.prerequisite_refs:
            raise ValueError("accepted dependency decisions require prerequisites")
        if self.disposition is DependencyDisposition.ADD_PREREQUISITE:
            _require_text(self.prerequisite_observable or "", "dependency prerequisite observable")

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "parent_requirement_ref": self.parent_requirement_ref,
            "prerequisite_refs": list(self.prerequisite_refs),
            "rationale": self.rationale,
            "prerequisite_observable": self.prerequisite_observable,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DependencyDecision":
        return cls(
            disposition=DependencyDisposition(str(payload["disposition"])),
            parent_requirement_ref=str(payload["parent_requirement_ref"]),
            prerequisite_refs=[str(item) for item in payload.get("prerequisite_refs", [])],
            rationale=str(payload["rationale"]),
            prerequisite_observable=payload.get("prerequisite_observable"),
        )


@dataclass(frozen=True)
class WorkPacketSplit:
    parent_work_unit_id: str
    child_work_unit_ids: list[str]
    preserved_objective: str
    rationale: str

    def __post_init__(self) -> None:
        _require_text(self.parent_work_unit_id, "split parent work unit id")
        _require_text(self.preserved_objective, "split preserved objective")
        _require_text(self.rationale, "split rationale")
        _string_list(self.child_work_unit_ids, "split child work unit ids")
        if len(self.child_work_unit_ids) < 2 or len(set(self.child_work_unit_ids)) != len(self.child_work_unit_ids):
            raise ValueError("a split requires at least two unique child work units")

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_work_unit_id": self.parent_work_unit_id,
            "child_work_unit_ids": list(self.child_work_unit_ids),
            "preserved_objective": self.preserved_objective,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkPacketSplit":
        return cls(
            parent_work_unit_id=str(payload["parent_work_unit_id"]),
            child_work_unit_ids=[str(item) for item in payload["child_work_unit_ids"]],
            preserved_objective=str(payload["preserved_objective"]),
            rationale=str(payload["rationale"]),
        )


@dataclass(frozen=True)
class UnclassifiedAnalysis:
    evidence_summary: str
    missing_category_description: str
    distinguishing_evidence: str

    def __post_init__(self) -> None:
        _require_text(self.evidence_summary, "unclassified evidence summary")
        _require_text(self.missing_category_description, "unclassified missing category description")
        _require_text(self.distinguishing_evidence, "unclassified distinguishing evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_summary": self.evidence_summary,
            "missing_category_description": self.missing_category_description,
            "distinguishing_evidence": self.distinguishing_evidence,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UnclassifiedAnalysis":
        return cls(
            evidence_summary=str(payload["evidence_summary"]),
            missing_category_description=str(payload["missing_category_description"]),
            distinguishing_evidence=str(payload["distinguishing_evidence"]),
        )


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
        _require_text(self.source, "failure observation source")
        _require_text(self.message, "failure observation message")
        _string_list(self.evidence_refs, "failure observation evidence refs")
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
        _require_text(self.role, "repair packet role")
        _require_text(self.work_unit_id, "repair packet work unit id")
        _require_text(self.original_objective, "repair packet objective")
        if not self.allowed_paths:
            raise ValueError("repair packet must preserve allowed paths")
        _string_list(self.allowed_paths, "repair packet allowed paths")
        _string_list(self.evidence, "repair packet evidence")
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
        classification = payload.get("classification")
        return cls(
            kind=PacketKind(str(payload["kind"])),
            role=str(payload["role"]),
            work_unit_id=str(payload["work_unit_id"]),
            trusted_revision=payload.get("trusted_revision"),
            original_objective=str(payload["original_objective"]),
            allowed_paths=[str(item) for item in payload["allowed_paths"]],
            classification=None if classification is None else FailureClassification(str(classification)),
            previous_candidate=payload.get("previous_candidate"),
            evidence=[str(item) for item in payload.get("evidence", [])],
        )
