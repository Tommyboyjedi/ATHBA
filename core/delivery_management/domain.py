"""Distinct application, branch and candidate authority records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from hashlib import sha256
from pathlib import Path

from core.project_setup.architecture import FullBehavior


class DeliveryPhase(str, Enum):
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETE = "branch_complete"
    FAILED = "failed"
    BLOCKED = "blocked"


class MergeKind(str, Enum):
    SYNCHRONIZATION = "synchronization"
    INTEGRATION = "integration"


class MergeStatus(str, Enum):
    NO_CHANGE = "no_change"
    REQUESTED = "requested"
    DEFERRED = "deferred"
    CONFLICT = "conflict"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True)
class TeamDelivery:
    id: str
    project_id: str
    behavior: FullBehavior
    architecture_sha256: str
    specification_version: int
    specification_sha256: str
    architecture_version: int
    branch_ref: str
    worktree: str
    state_root: str
    fork_revision: str
    synchronized_main: str
    trusted_revision: str
    scope_base_revision: str | None = None
    phase: DeliveryPhase = DeliveryPhase.READY
    worker_token: str | None = None
    completion_revision: str | None = None
    authority_file: str | None = None
    authority_sha256: str | None = None
    checkpoint_authority_file: str | None = None
    checkpoint_authority_sha256: str | None = None
    revision_intent: tuple[str, str] | None = None
    evidence_refs: tuple[str, ...] = ()
    unproven_assurance: tuple[dict, ...] = ()
    naming: str | None = None
    refactoring: str | None = None
    reason: str | None = None
    traceback: str | None = None
    pending_sync: bool = False
    pending_sync_revision: str | None = None
    synchronization_records: tuple[str, ...] = ()
    integration_records: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> TeamDelivery:
        value = dict(payload)
        behavior = dict(value["behavior"])
        for key in ("production_paths", "test_paths", "depends_on"):
            behavior[key] = tuple(behavior.get(key, ()))
        value["behavior"] = FullBehavior(**behavior)
        value["phase"] = DeliveryPhase(value["phase"])
        if value.get("revision_intent"):
            value["revision_intent"] = tuple(value["revision_intent"])
        for key in ("evidence_refs", "unproven_assurance", "synchronization_records", "integration_records"):
            value[key] = tuple(value.get(key, ()))
        return cls(**value)


@dataclass(frozen=True)
class MergeRecord:
    id: str
    project_id: str
    delivery_id: str
    kind: MergeKind
    main_revision: str
    delivery_revision: str
    status: MergeStatus = MergeStatus.REQUESTED
    candidate_revision: str | None = None
    authority_files: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    reason: str | None = None
    approval: ManagementApproval | None = None
    publication_intent: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> MergeRecord:
        value = dict(payload)
        value["kind"], value["status"] = MergeKind(value["kind"]), MergeStatus(value["status"])
        for key in ("authority_files", "evidence_refs", "conflicts"):
            value[key] = tuple(value.get(key, ()))
        if value.get("approval"):
            value["approval"] = ManagementApproval(**value["approval"])
        return cls(**value)


@dataclass(frozen=True)
class ManagementApproval:
    operation_id: str
    actor_reference: str
    main_revision: str
    delivery_revision: str
    candidate_revision: str
    authority_digest: str


@dataclass(frozen=True)
class ManagementRequest:
    project_id: str
    delivery_id: str
    actor_reference: str


@dataclass(frozen=True)
class DispatchPolicy:
    max_concurrency: int = 2

    def __post_init__(self) -> None:
        if self.max_concurrency < 1:
            raise ValueError("dispatch concurrency must be positive")


def delivery_identity(request: tuple[str, str, str]) -> str:
    return sha256(":".join(request).encode()).hexdigest()
