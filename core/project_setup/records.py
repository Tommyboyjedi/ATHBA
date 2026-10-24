"""Associated setup/delivery metadata, not another project identity or database."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from contextlib import contextmanager
import fcntl

from core.atomic_json_file import read_json_file, write_json_atomically
from core.filesystem_policy import resolve_identifier_path
from core.project_setup.commands import CommandResult, ToolObservation
from core.project_setup.architecture import FullBehavior


class SetupStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    FAILED = "failed"


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    COMPLETE_WITH_UNPROVEN_ASSURANCE = "complete_with_unproven_assurance"
    WAITING = "waiting"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryRecord:
    behavior_id: str
    run_id: str
    source_sha256: str
    architecture_sha256: str
    entry_revision: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    last_trusted_bde_revision: str | None = None
    accepted_revision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    unproven_assurance: tuple[str, ...] = ()
    naming: str | None = None
    refactoring: str | None = None
    reason: str | None = None
    traceback: str | None = None
    repository_progressed: bool = False
    repository_uncertain: bool = False
    observed_repository_revision: str | None = None
    reservation_ids: tuple[str, ...] = ()
    work_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectSetupRecord:
    project_id: str
    architecture_sha256: str
    specification_sha256: str
    profile_id: str
    technologies: tuple[str, ...]
    status: SetupStatus
    repository_root: str | None = None
    scaffold_revision: str | None = None
    last_accepted_revision: str | None = None
    environment_verified: bool = False
    bde_language_compatible: bool = False
    bde_shared_handoff_supported: bool = False
    reason: str | None = None
    tools: tuple[ToolObservation, ...] = ()
    commands: tuple[CommandResult, ...] = ()
    behavior_ids: tuple[str, ...] = ()
    behaviors: tuple[FullBehavior, ...] = ()
    bde_handoff_reason: str | None = None
    deliveries: tuple[DeliveryRecord, ...] = ()
    active_delivery: str | None = None
    approval_identity: str = ""
    approval_kind: str = ""
    setup_identity: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> ProjectSetupRecord:
        value = dict(payload)
        value["status"] = SetupStatus(value["status"])
        for key in ("technologies", "behavior_ids"):
            value[key] = tuple(value.get(key, ()))
        value["tools"] = tuple(ToolObservation(
            item["kind"], item["expected_version"], item["actual_version"], item["available"],
            CommandResult(tuple(item["result"]["argv"]), item["result"]["returncode"],
                          item["result"]["stdout"], item["result"]["stderr"]))
            for item in value.get("tools", ()))
        value["commands"] = tuple(CommandResult(tuple(item["argv"]), item["returncode"],
                                                item["stdout"], item["stderr"])
                                   for item in value.get("commands", ()))
        value["behaviors"] = tuple(FullBehavior(
            item["id"], item["source"], item["source_sha256"], tuple(item["production_paths"]),
            tuple(item["test_paths"]), tuple(item.get("depends_on", ())))
            for item in value.get("behaviors", ()))
        deliveries = []
        for item in value.get("deliveries", ()):
            entry = dict(item)
            entry["status"] = DeliveryStatus(entry["status"])
            for key in ("evidence_refs", "unproven_assurance", "reservation_ids", "work_ids"):
                entry[key] = tuple(entry.get(key, ()))
            deliveries.append(DeliveryRecord(**entry))
        value["deliveries"] = tuple(deliveries)
        return cls(**value)


@dataclass(frozen=True)
class ProjectSetupRepository:
    root: Path

    def path(self, project_id: str) -> Path:
        return resolve_identifier_path(self.root, project_id, "project id") / "architecture-setup.json"

    def load(self, project_id: str) -> ProjectSetupRecord | None:
        path = self.path(project_id)
        return ProjectSetupRecord.from_dict(read_json_file(path)) if path.exists() else None

    def save(self, record: ProjectSetupRecord) -> None:
        write_json_atomically(self.path(record.project_id), record.to_dict())

    @contextmanager
    def locked(self, project_id: str):
        path = self.path(project_id).with_suffix(".lock")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("another setup/delivery owns this project") from error
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
