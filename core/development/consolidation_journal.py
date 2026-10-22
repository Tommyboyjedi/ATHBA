"""Durable optional-work checkpoints; interrupted reasoning is never replayed."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
import fcntl
import hashlib
import json
from pathlib import Path
from typing import Any, Iterator

from core.atomic_json_file import read_json_file, write_json_atomically
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult


class ConsolidationOutcome(str, Enum):
    NO_CONSOLIDATION = "no_consolidation"
    REJECTED = "rejected"
    VERIFIED = "verified"


@dataclass(frozen=True)
class ConsolidationProgress:
    baseline_revision: str
    member_refs: tuple[str, ...] = ()
    test_revision: str | None = None
    final_revision: str | None = None
    outcome: ConsolidationOutcome | None = None
    diagnostic: str = ""
    supersession: dict[str, Any] | None = None
    reduction_evidence: str | None = None


class ConsolidationJournal:
    """Persist one completion's decisions before publishing its accepted pair."""

    def __init__(self, root: Path, identity: str):
        self.root = root / hashlib.sha256(identity.encode()).hexdigest()
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self) -> Iterator[None]:
        with (self.root / "lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self) -> ConsolidationProgress | None:
        path = self.root / "checkpoint.json"
        if not path.exists():
            return None
        item = read_json_file(path)
        item["member_refs"] = tuple(item["member_refs"])
        if item["outcome"] is not None:
            item["outcome"] = ConsolidationOutcome(item["outcome"])
        return ConsolidationProgress(**item)

    def save(self, progress: ConsolidationProgress) -> None:
        write_json_atomically(self.root / "checkpoint.json", asdict(progress))

    def record(self, item: tuple[str, Any]) -> None:
        name, value = item
        write_json_atomically(self.root / name, value)

    def recorded_call(self, item: tuple[str, ReasoningRequest]) -> ReasoningResult | None:
        phase, request = item
        path = self.root / (phase + ".json")
        digest = hashlib.sha256(json.dumps(asdict(request), sort_keys=True).encode()).hexdigest()
        if path.exists():
            saved = read_json_file(path)
            if saved["request_digest"] != digest:
                raise ValueError("consolidation reasoning authority changed on resume")
            if saved["status"] != "completed":
                raise ValueError("consolidation reasoning outcome uncertain; submission will not replay")
            return ReasoningResult(**saved["result"])
        write_json_atomically(path, {
            "request_digest": digest, "request": asdict(request), "status": "pending",
        })
        return None

    def complete_call(self, item: tuple[str, ReasoningResult]) -> None:
        phase, result = item
        path = self.root / (phase + ".json")
        value = read_json_file(path)
        if value["status"] != "pending":
            raise ValueError("consolidation response has no pending admission")
        write_json_atomically(path, {**value, "status": "completed", "result": asdict(result)})
