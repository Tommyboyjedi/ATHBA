from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.development.tdd_progression_validation import (
    enum_value,
    list_of_strings,
    normalize_evidence_kind,
    require_text,
    validate_list_of_strings,
    validate_unique_refs,
)
from core.development.tdd_progression_values import (
    ChecklistAssessmentStatus,
    ChecklistEvidenceKind,
    ChecklistItemKind,
    GatekeeperAssessmentStatus,
)


@dataclass(frozen=True)
class SourceRequirementClause:
    ref: str
    text: str
    kind: str
    evidence_kind: str = ChecklistEvidenceKind.TEST.value

    def __post_init__(self) -> None:
        require_text(self.ref, "source clause ref")
        require_text(self.text, "source clause text")
        object.__setattr__(self, "kind", enum_value(self.kind, ChecklistItemKind, "source clause kind"))
        object.__setattr__(self, "evidence_kind", normalize_evidence_kind(self.kind, self.evidence_kind))

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
            evidence_kind=normalize_evidence_kind(kind, payload.get("evidence_kind")),
        )


@dataclass(frozen=True)
class SpecificationChecklistItem:
    """One atomic source-specification fact, independent of proof strategy."""

    ref: str
    text: str
    kind: str

    def __post_init__(self) -> None:
        require_text(self.ref, "checklist item ref")
        require_text(self.text, "checklist item text")
        object.__setattr__(self, "kind", enum_value(self.kind, ChecklistItemKind, "checklist item kind"))

    def to_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "text": self.text, "kind": self.kind}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SpecificationChecklistItem":
        return cls(ref=str(payload["ref"]), text=str(payload["text"]), kind=str(payload["kind"]))


@dataclass(frozen=True)
class SpecificationChecklist:
    project_id: str
    requirement_text: str
    items: list[SpecificationChecklistItem | SourceRequirementClause]

    def __post_init__(self) -> None:
        require_text(self.project_id, "checklist project id")
        require_text(self.requirement_text, "checklist requirement text")
        if not self.items:
            raise ValueError("specification checklist items must not be empty")
        validate_unique_refs([item.ref for item in self.items], "checklist item refs")

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
            items=[SpecificationChecklistItem.from_dict(dict(item)) for item in items],
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
        require_text(self.checklist_ref, "checklist evidence ref")
        object.__setattr__(self, "evidence_kind", enum_value(self.evidence_kind, ChecklistEvidenceKind, "checklist evidence kind"))
        require_text(self.status, "checklist evidence status")
        for value, label in (
            (self.test_name, "checklist evidence test name"),
            (self.test_path, "checklist evidence test path"),
            (self.step_id, "checklist evidence step id"),
            (self.requirement_ref, "checklist evidence requirement ref"),
            (self.accepted_revision, "checklist evidence accepted revision"),
            (self.semantic_revision, "checklist evidence semantic revision"),
            (self.evidence_location, "checklist evidence location"),
            (self.rationale, "checklist evidence rationale"),
        ):
            if value is not None:
                require_text(value, label)
        if self.evidence_kind == ChecklistEvidenceKind.TEST.value:
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
        require_text(self.checklist_ref, "specification gap checklist ref")
        require_text(self.obligation_text, "specification gap obligation text")
        object.__setattr__(self, "item_kind", enum_value(self.item_kind, ChecklistItemKind, "specification gap item kind"))
        require_text(self.reason, "specification gap reason")
        require_text(self.desired_proof, "specification gap desired proof")
        validate_list_of_strings(self.related_test_names, "specification gap related test names")
        require_text(self.status, "specification gap status")

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
            related_test_names=list_of_strings(payload.get("related_test_names", []), "specification gap related test names"),
            status=str(payload.get("status", "open")),
        )


@dataclass(frozen=True)
class ChecklistItemAssessment:
    checklist_ref: str
    status: str
    rationale: str
    evidence: list[ChecklistEvidence] = field(default_factory=list)

    def __post_init__(self) -> None:
        require_text(self.checklist_ref, "checklist assessment ref")
        object.__setattr__(self, "status", enum_value(self.status, ChecklistAssessmentStatus, "checklist assessment status"))
        require_text(self.rationale, "checklist assessment rationale")
        if self.status == ChecklistAssessmentStatus.PROVEN.value and not self.evidence:
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
        object.__setattr__(self, "status", enum_value(self.status, GatekeeperAssessmentStatus, "gatekeeper assessment status"))
        if not self.item_assessments:
            raise ValueError("gatekeeper item assessments must not be empty")
        validate_unique_refs([item.checklist_ref for item in self.item_assessments], "gatekeeper assessment refs")
        if self.assessed_at is not None:
            require_text(self.assessed_at, "gatekeeper assessed at")

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
        return self.latest_assessment is not None and self.latest_assessment.status == GatekeeperAssessmentStatus.COMPLETE.value

    def unresolved_item_refs(self) -> list[str]:
        if self.latest_assessment is None:
            return self.checklist.item_refs()
        return [item.checklist_ref for item in self.latest_assessment.item_assessments if item.status != ChecklistAssessmentStatus.PROVEN.value]

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
