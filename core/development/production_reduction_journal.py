"""Atomic, identity-bound evidence for resumable deterministic experiments."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, replace
import fcntl
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterator

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.microcycle_domain import RegressionState
from core.development.production_reduction_domain import (
    ProductionReductionRequest, ReductionCheckpoint, ReductionPolicy,
)


def authority(request: ProductionReductionRequest) -> dict[str, Any]:
    payload = asdict(request)
    payload.pop("cancelled")
    payload["repository_root"] = str(request.repository_root.resolve())
    return json.loads(json.dumps(payload, sort_keys=True))


class ReductionJournal:
    """Locks and serializes only one frozen B/R/I/C and acceptance identity."""

    def __init__(self, root: Path, request: ProductionReductionRequest):
        self.authority = authority(request)
        encoded = json.dumps(self.authority, sort_keys=True).encode()
        self.identity = hashlib.sha256(encoded).hexdigest()
        self.root = root / self.identity
        self.root.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self) -> Iterator[None]:
        with (self.root / "lock").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def load(self, policy: ReductionPolicy) -> ReductionCheckpoint | None:
        path = self.root / "checkpoint.json"
        if not path.exists():
            return None
        value = read_json_file(path)
        if value["authority"] != self.authority or value["policy"] != asdict(policy):
            raise ValueError("reduction authority or policy changed on resume")
        item = value["checkpoint"]
        item["regression"] = RegressionState.from_dict(item["regression"])
        for name in ("tried_ids", "tried_states", "limitations"):
            item[name] = tuple(item[name])
        checkpoint = ReductionCheckpoint(**item)
        if checkpoint.identity != self.identity:
            raise ValueError("reduction checkpoint identity mismatch")
        return checkpoint

    def save(self, item: tuple[ReductionCheckpoint, ReductionPolicy]) -> None:
        checkpoint, policy = item
        write_json_atomically(self.root / "checkpoint.json", {
            "authority": self.authority, "policy": asdict(policy),
            "checkpoint": asdict(checkpoint), "residual_minimality": "unknown",
        })

    def record(self, item: tuple[str, dict[str, Any]]) -> None:
        name, payload = item
        write_json_atomically(self.root / name, payload)


    def discard_pending(self, item: tuple[int, str]) -> None:
        number, reason = item
        path = self.root / f"trial-{number:04d}.json"
        if path.exists():
            value = read_json_file(path)
            if value.get("decision") == "pending":
                write_json_atomically(path, {**value, "decision": "discarded", "reason": reason})


    @contextmanager
    def measured(self, policy: ReductionPolicy) -> Iterator[None]:
        started = time.monotonic()
        prior = self.load(policy)
        before = prior.elapsed_seconds if prior else 0.0
        try:
            yield
        finally:
            current = self.load(policy)
            if current is not None:
                elapsed = max(current.elapsed_seconds, before + time.monotonic() - started)
                self.save((replace(current, elapsed_seconds=elapsed), policy))
