"""Language-neutral authority and durable evidence for structural recovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

DEFAULT_STRUCTURAL_ATTEMPTS = 4
DEFAULT_STRUCTURAL_TIMEOUT_SECONDS = 300


class StructuralPhase(str, Enum):
    PENDING = "pending"
    STARTED = "started"
    VALIDATING = "validating"
    RERUN = "rerun"
    PROMOTING = "promoting"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class StructuralProblem:
    description: str
    production_path: str
    scope_start: int
    scope_end: int
    subject: str

    def __post_init__(self) -> None:
        if not all((self.description.strip(), self.production_path.strip(), self.subject.strip())):
            raise ValueError("structural problem requires normalized authority")
        if self.scope_start < 1 or self.scope_end < self.scope_start:
            raise ValueError("structural problem requires a bounded production span")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> StructuralProblem:
        return cls(str(value["description"]), str(value["production_path"]),
                   int(value["scope_start"]), int(value["scope_end"]), str(value["subject"]))


@dataclass(frozen=True)
class StructuralProductionSource:
    problem: StructuralProblem
    source: str


@dataclass(frozen=True)
class StructuralCandidateCheck:
    problem: StructuralProblem
    original_source: str
    candidate_source: str


@dataclass(frozen=True)
class StructuralRefactorPolicy:
    max_attempts: int = DEFAULT_STRUCTURAL_ATTEMPTS
    timeout_seconds: int = DEFAULT_STRUCTURAL_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.timeout_seconds < 1:
            raise ValueError("structural bounds must be positive")


@dataclass(frozen=True)
class StructuralAttempt:
    identity: str
    frontier_index: int
    trusted_revision: str
    phase: StructuralPhase = StructuralPhase.STARTED
    candidate_revision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    reason: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> StructuralAttempt:
        return cls(str(value["identity"]), int(value["frontier_index"]),
                   str(value["trusted_revision"]), StructuralPhase(value["phase"]),
                   value.get("candidate_revision"), tuple(value.get("evidence_refs", ())),
                   str(value.get("reason", "")))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
