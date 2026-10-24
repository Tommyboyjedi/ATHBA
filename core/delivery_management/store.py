"""Atomic associated records and per-operation Linux file ownership."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from pathlib import Path
from typing import Callable

from core.atomic_json_file import read_json_file, write_json_atomically
from core.filesystem_policy import resolve_identifier_path
from core.delivery_management.domain import TeamDelivery, MergeRecord


@dataclass(frozen=True)
class RecordIdentity:
    project_id: str
    record_id: str


@dataclass(frozen=True)
class ManagementStore:
    project_root: Path

    def directory(self, project_id: str) -> Path:
        return resolve_identifier_path(self.project_root, project_id, "project id") / "delivery-management"

    def path(self, request: tuple[RecordIdentity, str]) -> Path:
        identity, category = request
        return resolve_identifier_path(self.directory(identity.project_id) / category,
                                       identity.record_id, "record id").with_suffix(".json")

    def delivery(self, identity: RecordIdentity) -> TeamDelivery | None:
        path = self.path((identity, "deliveries"))
        return TeamDelivery.from_dict(read_json_file(path)) if path.exists() else None

    def save_delivery(self, value: TeamDelivery) -> None:
        write_json_atomically(self.path((RecordIdentity(value.project_id, value.id), "deliveries")), value.to_dict())

    def merge(self, identity: RecordIdentity) -> MergeRecord | None:
        path = self.path((identity, "merges"))
        return MergeRecord.from_dict(read_json_file(path)) if path.exists() else None

    def save_merge(self, value: MergeRecord) -> None:
        write_json_atomically(self.path((RecordIdentity(value.project_id, value.id), "merges")), value.to_dict())

    def deliveries(self, project_id: str) -> tuple[TeamDelivery, ...]:
        root = self.directory(project_id) / "deliveries"
        return tuple(TeamDelivery.from_dict(read_json_file(path)) for path in sorted(root.glob("*.json")))

    def merges(self, project_id: str) -> tuple[MergeRecord, ...]:
        return tuple(MergeRecord.from_dict(read_json_file(path))
                     for path in sorted((self.directory(project_id) / "merges").glob("*.json")))

    def update_delivery(self, request: tuple[RecordIdentity, Callable[[TeamDelivery], TeamDelivery]]) -> TeamDelivery:
        identity, update = request
        with self.locked((identity.project_id, "metadata-" + identity.record_id)):
            current = self.delivery(identity)
            if current is None:
                raise ValueError("unknown delivery")
            result = update(current)
            self.save_delivery(result)
            return result

    def catalog(self, project_id: str) -> dict:
        path = self.directory(project_id) / "accepted-main.json"
        return read_json_file(path) if path.exists() else {}

    def save_catalog(self, request: tuple[str, dict]) -> None:
        project_id, value = request
        write_json_atomically(self.directory(project_id) / "accepted-main.json", value)

    @contextmanager
    def locked(self, request: tuple[str, str]):
        project_id, key = request
        root = self.directory(project_id) / "locks"
        path = resolve_identifier_path(root, key, "lock identity")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("management mutation already owned: " + key) from error
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
