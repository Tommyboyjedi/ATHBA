"""Typed feature-level state for the PR23 strict-TDD application composition."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
from typing import Any


class StrictTddFeatureStatus(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
    return value


def _texts(values: tuple[str, ...], label: str) -> None:
    if not values or any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")


@dataclass(frozen=True)
class StrictTddFeatureRequest:
    project_id: str
    source_requirement: str
    language_id: str
    test_framework: str
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]
    runtime_identity: str
    resume_policy: str
    checkpoint_policy: str | None
    evidence_root: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.project_id, "project id"),
            (self.source_requirement, "source requirement"),
            (self.language_id, "language id"),
            (self.test_framework, "test framework"),
            (self.runtime_identity, "runtime identity"),
            (self.resume_policy, "resume policy"),
            (self.evidence_root, "evidence root"),
        ):
            _text(value, label)
        _texts(self.production_paths, "production paths")
        _texts(self.test_paths, "test paths")
        if self.checkpoint_policy is not None:
            _text(self.checkpoint_policy, "checkpoint policy")

    @property
    def source_requirement_hash(self) -> str:
        return sha256(self.source_requirement.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CompletedBehaviorReference:
    behavior_ref: str
    scenario_id: str
    canonical_revision: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.behavior_ref, "completed behavior ref")
        _text(self.scenario_id, "completed scenario id")
        _text(self.canonical_revision, "completed canonical revision")
        _texts(self.evidence_refs, "completed evidence")


@dataclass(frozen=True)
class StrictTddFeatureState:
    project_id: str
    source_requirement_hash: str
    status: str
    contract_payload: dict[str, object] | None = None
    gatekeeper_payload: dict[str, object] | None = None
    current_scenario_id: str | None = None
    completed_behaviors: tuple[CompletedBehaviorReference, ...] = ()
    canonical_ref: str | None = None
    canonical_development_base: str | None = None
    working_ref: str | None = None
    working_revision: str | None = None
    blocked_reason: str | None = None
    final_reconciliation: tuple[dict[str, object], ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.project_id, "project id")
        _text(self.source_requirement_hash, "source requirement hash")
        if self.status not in {item.value for item in StrictTddFeatureStatus}:
            raise ValueError("unsupported feature status")
        if (self.canonical_ref is None) != (self.canonical_development_base is None):
            raise ValueError("canonical ref and development base must be paired")
        if (self.working_ref is None) != (self.working_revision is None):
            raise ValueError("working ref and revision must be paired")
        if self.status == StrictTddFeatureStatus.BLOCKED.value and not self.blocked_reason:
            raise ValueError("blocked feature state requires a reason")
        if any(not item.strip() for item in self.evidence_refs):
            raise ValueError("feature evidence refs must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "completed_behaviors": [asdict(item) for item in self.completed_behaviors],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrictTddFeatureState":
        completed = tuple(
            CompletedBehaviorReference(
                str(item["behavior_ref"]), str(item["scenario_id"]),
                str(item["canonical_revision"]), tuple(str(ref) for ref in item["evidence_refs"]),
            )
            for item in payload.get("completed_behaviors", ())
        )
        return cls(
            str(payload["project_id"]), str(payload["source_requirement_hash"]),
            str(payload["status"]), payload.get("contract_payload"),
            payload.get("gatekeeper_payload"), payload.get("current_scenario_id"),
            completed, payload.get("canonical_ref"), payload.get("canonical_development_base"),
            payload.get("working_ref"), payload.get("working_revision"),
            payload.get("blocked_reason"), tuple(payload.get("final_reconciliation", ())),
            tuple(str(item) for item in payload.get("evidence_refs", ())),
        )


@dataclass(frozen=True)
class StrictTddFeatureResult:
    project_id: str
    project_path: str
    current_status: str
    canonical_ref: str | None
    canonical_development_base: str | None
    working_ref: str | None
    working_revision: str | None
    current_scenario_id: str | None
    completed_behaviors: tuple[CompletedBehaviorReference, ...]
    blocked_reason: str | None
    final_reconciliation: tuple[dict[str, object], ...]
    evidence_refs: tuple[str, ...]