from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from core.development.tdd_progression_validation import (
    enum_value,
    list_of_strings,
    require_text,
    validate_list_of_strings,
    validate_unique_refs,
)


class ProvisionalRequirementStatus(str, Enum):
    PROVISIONAL = "provisional"


class SemanticObligationStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class SemanticObligationDraft:
    owning_requirement_ref: str
    blocking_requirement_refs: list[str]
    rationale: str
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        require_text(self.owning_requirement_ref, "obligation owning requirement ref")
        if not self.blocking_requirement_refs:
            raise ValueError("semantic obligation drafts require at least one blocking requirement ref")
        validate_list_of_strings(self.blocking_requirement_refs, "obligation blocking requirement refs")
        require_text(self.rationale, "semantic obligation rationale")
        validate_list_of_strings(self.evidence_refs, "semantic obligation evidence refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "owning_requirement_ref": self.owning_requirement_ref,
            "blocking_requirement_refs": list(self.blocking_requirement_refs),
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticObligationDraft":
        return cls(
            owning_requirement_ref=str(payload["owning_requirement_ref"]),
            blocking_requirement_refs=list_of_strings(
                payload.get("blocking_requirement_refs", []),
                "obligation blocking requirement refs",
            ),
            rationale=str(payload["rationale"]),
            evidence_refs=list_of_strings(payload.get("evidence_refs", []), "semantic obligation evidence refs"),
        )


@dataclass(frozen=True)
class OpenSemanticObligation:
    obligation_id: str
    owning_requirement_ref: str
    blocking_requirement_refs: list[str]
    rationale: str
    evidence_refs: list[str]
    originating_step_id: str
    introduced_revision: str
    status: str = SemanticObligationStatus.OPEN.value

    def __post_init__(self) -> None:
        require_text(self.obligation_id, "semantic obligation id")
        require_text(self.owning_requirement_ref, "semantic obligation owning requirement ref")
        if not self.blocking_requirement_refs:
            raise ValueError("open semantic obligations require at least one blocking requirement ref")
        validate_list_of_strings(self.blocking_requirement_refs, "semantic obligation blocking requirement refs")
        require_text(self.rationale, "semantic obligation rationale")
        validate_list_of_strings(self.evidence_refs, "semantic obligation evidence refs")
        require_text(self.originating_step_id, "semantic obligation originating step id")
        require_text(self.introduced_revision, "semantic obligation introduced revision")
        object.__setattr__(self, "status", enum_value(self.status, SemanticObligationStatus, "semantic obligation status"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "owning_requirement_ref": self.owning_requirement_ref,
            "blocking_requirement_refs": list(self.blocking_requirement_refs),
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            "originating_step_id": self.originating_step_id,
            "introduced_revision": self.introduced_revision,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OpenSemanticObligation":
        return cls(
            obligation_id=str(payload["obligation_id"]),
            owning_requirement_ref=str(payload["owning_requirement_ref"]),
            blocking_requirement_refs=list_of_strings(
                payload.get("blocking_requirement_refs", []),
                "semantic obligation blocking requirement refs",
            ),
            rationale=str(payload["rationale"]),
            evidence_refs=list_of_strings(payload.get("evidence_refs", []), "semantic obligation evidence refs"),
            originating_step_id=str(payload["originating_step_id"]),
            introduced_revision=str(payload["introduced_revision"]),
            status=str(payload.get("status", SemanticObligationStatus.OPEN.value)),
        )


@dataclass(frozen=True)
class ObligationResolutionRecord:
    obligation_id: str
    owning_requirement_ref: str
    resolved_by_requirement_refs: list[str]
    resolution_revision: str
    rationale: str

    def __post_init__(self) -> None:
        require_text(self.obligation_id, "obligation resolution id")
        require_text(self.owning_requirement_ref, "obligation resolution owning requirement ref")
        if not self.resolved_by_requirement_refs:
            raise ValueError("obligation resolution requires at least one resolving requirement ref")
        validate_list_of_strings(self.resolved_by_requirement_refs, "obligation resolution requirement refs")
        require_text(self.resolution_revision, "obligation resolution revision")
        require_text(self.rationale, "obligation resolution rationale")

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "owning_requirement_ref": self.owning_requirement_ref,
            "resolved_by_requirement_refs": list(self.resolved_by_requirement_refs),
            "resolution_revision": self.resolution_revision,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ObligationResolutionRecord":
        return cls(
            obligation_id=str(payload["obligation_id"]),
            owning_requirement_ref=str(payload["owning_requirement_ref"]),
            resolved_by_requirement_refs=list_of_strings(
                payload.get("resolved_by_requirement_refs", []),
                "obligation resolution requirement refs",
            ),
            resolution_revision=str(payload["resolution_revision"]),
            rationale=str(payload["rationale"]),
        )


@dataclass(frozen=True)
class ProvisionalRequirementState:
    requirement_ref: str
    development_revision: str
    originating_step_id: str
    accepted_test_names: list[str]
    open_obligation_ids: list[str]
    status: str = ProvisionalRequirementStatus.PROVISIONAL.value

    def __post_init__(self) -> None:
        require_text(self.requirement_ref, "provisional requirement ref")
        require_text(self.development_revision, "provisional development revision")
        require_text(self.originating_step_id, "provisional originating step id")
        if not self.accepted_test_names:
            raise ValueError("provisional requirements require at least one accepted test name")
        validate_list_of_strings(self.accepted_test_names, "provisional accepted test names")
        validate_list_of_strings(self.open_obligation_ids, "provisional open obligation ids")
        object.__setattr__(self, "status", enum_value(self.status, ProvisionalRequirementStatus, "provisional requirement status"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "requirement_ref": self.requirement_ref,
            "development_revision": self.development_revision,
            "originating_step_id": self.originating_step_id,
            "accepted_test_names": list(self.accepted_test_names),
            "open_obligation_ids": list(self.open_obligation_ids),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProvisionalRequirementState":
        return cls(
            requirement_ref=str(payload["requirement_ref"]),
            development_revision=str(payload["development_revision"]),
            originating_step_id=str(payload["originating_step_id"]),
            accepted_test_names=list_of_strings(payload.get("accepted_test_names", []), "provisional accepted test names"),
            open_obligation_ids=list_of_strings(payload.get("open_obligation_ids", []), "provisional open obligation ids"),
            status=str(payload.get("status", ProvisionalRequirementStatus.PROVISIONAL.value)),
        )


@dataclass(frozen=True)
class SemanticProgressLedger:
    provisional_requirements: list[ProvisionalRequirementState] = field(default_factory=list)
    open_obligations: list[OpenSemanticObligation] = field(default_factory=list)
    resolution_history: list[ObligationResolutionRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_unique_refs(
            [item.requirement_ref for item in self.provisional_requirements],
            "provisional requirement refs",
        )
        validate_unique_refs(
            [item.obligation_id for item in self.open_obligations],
            "semantic obligation ids",
        )
        validate_unique_refs(
            [item.obligation_id for item in self.resolution_history],
            "semantic obligation resolution ids",
        )
        known_ids = {item.obligation_id for item in self.open_obligations}
        for item in self.provisional_requirements:
            missing = [obligation_id for obligation_id in item.open_obligation_ids if obligation_id not in known_ids]
            if missing:
                raise ValueError("provisional requirement referenced unknown open obligation ids")

    def provisional_requirement_refs(self) -> set[str]:
        return {item.requirement_ref for item in self.provisional_requirements}

    def open_requirement_refs(self) -> set[str]:
        return {item.owning_requirement_ref for item in self.open_obligations if item.status == SemanticObligationStatus.OPEN.value}

    def open_obligation_ids_for(self, requirement_ref: str) -> set[str]:
        return {
            item.obligation_id
            for item in self.open_obligations
            if item.owning_requirement_ref == requirement_ref and item.status == SemanticObligationStatus.OPEN.value
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "provisional_requirements": [item.to_dict() for item in self.provisional_requirements],
            "open_obligations": [item.to_dict() for item in self.open_obligations],
            "resolution_history": [item.to_dict() for item in self.resolution_history],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SemanticProgressLedger":
        return cls(
            provisional_requirements=[
                ProvisionalRequirementState.from_dict(dict(item))
                for item in payload.get("provisional_requirements", [])
            ],
            open_obligations=[
                OpenSemanticObligation.from_dict(dict(item))
                for item in payload.get("open_obligations", [])
            ],
            resolution_history=[
                ObligationResolutionRecord.from_dict(dict(item))
                for item in payload.get("resolution_history", [])
            ],
        )
