"""Persistent records for bounded Tester scenario drafting."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from core.development.microcycle_domain import MicrocycleState, ScenarioIntentResult
from core.development.tdd_progression import TddStepProposal

MAX_TESTER_SCENARIO_ATTEMPTS = 4


class ScenarioDraftStatus(str, Enum):
    DRAFTING = "drafting"
    APPROVED = "approved"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


@dataclass(frozen=True)
class ScenarioRepositoryFacts:
    trusted_revision: str
    visible_paths: tuple[str, ...]
    production_excerpt: str
    test_excerpt: str

    def __post_init__(self) -> None:
        if not self.trusted_revision.strip():
            raise ValueError("repository facts require a trusted revision")
        if any(not item.strip() for item in self.visible_paths):
            raise ValueError("repository paths must be non-empty")


@dataclass(frozen=True)
class ScenarioDraftRequest:
    scenario_id: str
    ticket: TddStepProposal
    source_requirement_refs: tuple[str, ...]
    language_id: str
    test_framework: str
    allowed_test_path: str
    repository_facts: ScenarioRepositoryFacts
    development_base_revision: str

    def __post_init__(self) -> None:
        values = (
            self.scenario_id,
            self.language_id,
            self.test_framework,
            self.allowed_test_path,
            self.development_base_revision,
        )
        if any(not value.strip() for value in values):
            raise ValueError("scenario draft request fields must be non-empty")
        if not self.source_requirement_refs or any(not value.strip() for value in self.source_requirement_refs):
            raise ValueError("scenario draft request requires source requirement refs")
        if self.allowed_test_path != self.ticket.test_path:
            raise ValueError("scenario draft path must match the behavior ticket")
        if self.repository_facts.trusted_revision != self.development_base_revision:
            raise ValueError("repository facts must match the development base")


@dataclass(frozen=True)
class ScenarioDraftAttempt:
    attempt_number: int
    work_unit_id: str
    change_id: str | None
    candidate_revision: str | None
    evidence_location: str | None
    status: str
    feedback: str | None = None
    intent: ScenarioIntentResult | None = None

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("scenario draft attempt number must be positive")
        if not self.work_unit_id.strip() or not self.status.strip():
            raise ValueError("scenario draft attempt fields must be non-empty")
        if self.feedback is not None and not self.feedback.strip():
            raise ValueError("scenario draft feedback must be non-empty when supplied")

    def to_dict(self) -> dict[str, object]:
        return {
            **asdict(self),
            "intent": None if self.intent is None else self.intent.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioDraftAttempt":
        intent = value.get("intent")
        return cls(
            attempt_number=int(value["attempt_number"]),
            work_unit_id=str(value["work_unit_id"]),
            change_id=value.get("change_id"),
            candidate_revision=value.get("candidate_revision"),
            evidence_location=value.get("evidence_location"),
            status=str(value["status"]),
            feedback=value.get("feedback"),
            intent=None if intent is None else ScenarioIntentResult.from_dict(dict(intent)),
        )


@dataclass(frozen=True)
class ScenarioDraftRunState:
    scenario_id: str
    behavior_ref: str
    source_requirement_refs: tuple[str, ...]
    language_id: str
    test_framework: str
    allowed_test_path: str
    development_base_revision: str
    attempts: tuple[ScenarioDraftAttempt, ...] = ()
    approved_microcycle: MicrocycleState | None = None
    status: str = ScenarioDraftStatus.DRAFTING.value
    project_synchronised: bool = False

    def __post_init__(self) -> None:
        values = (
            self.scenario_id,
            self.behavior_ref,
            self.language_id,
            self.test_framework,
            self.allowed_test_path,
            self.development_base_revision,
            self.status,
        )
        if any(not value.strip() for value in values):
            raise ValueError("scenario draft state fields must be non-empty")
        if not self.source_requirement_refs or any(not value.strip() for value in self.source_requirement_refs):
            raise ValueError("scenario draft state requires source requirement refs")
        if self.status not in {item.value for item in ScenarioDraftStatus}:
            raise ValueError("unsupported scenario draft status")
        if self.approved_microcycle is not None and self.status != ScenarioDraftStatus.APPROVED.value:
            raise ValueError("approved scenario state must have approved status")
        if len(self.attempts) > MAX_TESTER_SCENARIO_ATTEMPTS:
            raise ValueError("scenario draft attempt cap exceeded")

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "behavior_ref": self.behavior_ref,
            "source_requirement_refs": list(self.source_requirement_refs),
            "language_id": self.language_id,
            "test_framework": self.test_framework,
            "allowed_test_path": self.allowed_test_path,
            "development_base_revision": self.development_base_revision,
            "attempts": [item.to_dict() for item in self.attempts],
            "approved_microcycle": None if self.approved_microcycle is None else self.approved_microcycle.to_dict(),
            "status": self.status,
            "project_synchronised": self.project_synchronised,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioDraftRunState":
        approved = value.get("approved_microcycle")
        return cls(
            scenario_id=str(value["scenario_id"]),
            behavior_ref=str(value["behavior_ref"]),
            source_requirement_refs=tuple(str(item) for item in value["source_requirement_refs"]),
            language_id=str(value["language_id"]),
            test_framework=str(value["test_framework"]),
            allowed_test_path=str(value["allowed_test_path"]),
            development_base_revision=str(value["development_base_revision"]),
            attempts=tuple(ScenarioDraftAttempt.from_dict(dict(item)) for item in value.get("attempts", ())),
            approved_microcycle=None if approved is None else MicrocycleState.from_dict(dict(approved)),
            status=str(value.get("status", ScenarioDraftStatus.DRAFTING.value)),
            project_synchronised=bool(value.get("project_synchronised", False)),
        )


@dataclass(frozen=True)
class ScenarioDraftOutcome:
    state: ScenarioDraftRunState
    submitted_attempt: bool

    @property
    def approved(self) -> bool:
        return self.state.approved_microcycle is not None
