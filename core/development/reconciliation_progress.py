"""Typed checkpoints serialized through the existing feature-state repository."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Callable

from core.development.reconciliation_response import (
    ReconciliationAttempt, ReconciliationFailure, ReconciliationFailureKind,
)
from core.development.specification_domain import SpecificationChecklistItem

PROGRESS_SCHEMA = "gatekeeper-progress/v1"


def evidence_digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def incompatible(diagnostic: str) -> ReconciliationFailure:
    return ReconciliationFailure(ReconciliationFailureKind.INCOMPATIBLE_PROGRESS, diagnostic)


@dataclass(frozen=True)
class IndividualEvidenceProgress:
    checklist_ref: str
    test_name: str
    evidence_identity: str
    trusted_revision: str
    evaluation_order: int
    answer: str
    rationale: str
    response_attempts: tuple[ReconciliationAttempt, ...]

    def __post_init__(self) -> None:
        if self.answer not in {"YES", "NO"} or self.evaluation_order < 0 or not self.response_attempts:
            raise ValueError("invalid individual reconciliation progress")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "response_attempts": [asdict(item) for item in self.response_attempts]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> IndividualEvidenceProgress:
        return cls(**{**value, "response_attempts": tuple(
            ReconciliationAttempt(**entry) for entry in value["response_attempts"])})


class PendingReconciliationCall(str, Enum):
    NONE = ""
    TEST = "individual_test"
    SPLIT = "checklist_split"


@dataclass(frozen=True)
class ChecklistSplitProgress:
    disposition: str
    rationale: str
    children: tuple[SpecificationChecklistItem, ...] = ()
    attempted_response: str = ""
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if (self.disposition not in {"split", "unsplittable"} or not self.rationale.strip()
                or (self.disposition == "split" and len(self.children) < 2)
                or (self.disposition == "unsplittable" and self.children)):
            raise ValueError("invalid persisted checklist split")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "children": [item.to_dict() for item in self.children]}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ChecklistSplitProgress:
        return cls(**{**value, "children": tuple(SpecificationChecklistItem.from_dict(child)
                                                for child in value["children"])})


@dataclass(frozen=True)
class ChecklistItemProgress:
    item: SpecificationChecklistItem
    trusted_revision: str
    evidence_identity: str
    ancestry: tuple[str, ...]
    individual_attempts: tuple[IndividualEvidenceProgress, ...] = ()
    result: dict[str, Any] | None = None
    split: ChecklistSplitProgress | None = None
    pending_call: PendingReconciliationCall = PendingReconciliationCall.NONE

    def __post_init__(self) -> None:
        if not self.trusted_revision or not self.evidence_identity:
            raise ValueError("reconciliation checkpoint requires revision and evidence identity")
        names = [attempt.test_name for attempt in self.individual_attempts]
        if len(names) != len(set(names)):
            raise ValueError("duplicate individual evidence checkpoint")
        for index, attempt in enumerate(self.individual_attempts):
            if (attempt.checklist_ref != self.item.ref or attempt.trusted_revision != self.trusted_revision
                    or attempt.evaluation_order != index
                    or (attempt.answer == "YES" and index != len(self.individual_attempts) - 1)):
                raise ValueError("individual checkpoint identity or evaluation order differs")
        if self.result is not None and "individual_test_attempts" in self.result:
            if self.result["individual_test_attempts"] != [item.to_dict() for item in self.individual_attempts]:
                raise ValueError("completed result differs from individual checkpoints")

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "schema": PROGRESS_SCHEMA, "item": self.item.to_dict(),
                "individual_attempts": [attempt.to_dict() for attempt in self.individual_attempts],
                "split": None if self.split is None else self.split.to_dict(),
                "pending_call": self.pending_call.value}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ChecklistItemProgress:
        if value["schema"] != PROGRESS_SCHEMA:
            raise ValueError("unsupported reconciliation progress schema")
        return cls(SpecificationChecklistItem.from_dict(value["item"]), value["trusted_revision"],
                   value["evidence_identity"], tuple(value["ancestry"]),
                   tuple(IndividualEvidenceProgress.from_dict(item) for item in value["individual_attempts"]),
                   value["result"], None if value["split"] is None else ChecklistSplitProgress.from_dict(value["split"]),
                   PendingReconciliationCall(value["pending_call"]))


@dataclass(frozen=True)
class ReconciliationJournalRequest:
    trusted_revision: str
    evidence_identity: str
    progress: tuple[dict[str, object], ...] = ()
    checkpoint: Callable[[tuple[dict[str, object], ...]], None] | None = None
    root_refs: tuple[str, ...] = ()


class ReconciliationJournal:
    """Upsert one typed item checkpoint; never append duplicate item records."""

    def __init__(self, request: ReconciliationJournalRequest):
        self.request = request
        try:
            self.items = [ChecklistItemProgress.from_dict(item) for item in request.progress]
        except (KeyError, TypeError, ValueError) as error:
            raise incompatible("persisted reconciliation progress cannot be decoded") from error
        refs = [entry.item.ref for entry in self.items]
        if len(refs) != len(set(refs)):
            raise incompatible("duplicate persisted checklist progress")
        for entry in self.items:
            if (entry.trusted_revision != request.trusted_revision
                    or entry.evidence_identity != request.evidence_identity):
                raise incompatible("trusted revision or verified accepted-test evidence changed")

    def restore(self, item: SpecificationChecklistItem, ancestry: tuple[str, ...]) -> ChecklistItemProgress:
        existing = next((entry for entry in self.items if entry.item.ref == item.ref), None)
        if existing is None:
            return ChecklistItemProgress(item, self.request.trusted_revision, self.request.evidence_identity, ancestry)
        if existing.item != item or existing.ancestry != ancestry:
            raise incompatible("persisted checklist identity or ancestry changed")
        if existing.pending_call != PendingReconciliationCall.NONE:
            raise ReconciliationFailure(ReconciliationFailureKind.INTERRUPTED,
                                        "reconciliation call started without a durable result", item.ref)
        return existing

    def save(self, item: ChecklistItemProgress) -> None:
        index = next((index for index, entry in enumerate(self.items) if entry.item.ref == item.item.ref), None)
        if index is None:
            self.items.append(item)
        else:
            self.items[index] = item
        if self.request.checkpoint is not None:
            self.request.checkpoint(tuple(entry.to_dict() for entry in self.items))
