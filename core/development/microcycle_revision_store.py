"""Focused file repository for microcycle revision state."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.microcycle_revision_state import MicrocycleRevisionState


@dataclass
class MicrocycleRevisionRepository:
    root: Path

    def __init__(self, root: str | Path):
        object.__setattr__(self, "root", Path(root).resolve())

    def load(self, scenario_id: str) -> MicrocycleRevisionState | None:
        path = self._path_for(scenario_id)
        if not path.exists():
            return None
        return MicrocycleRevisionState.from_dict(read_json_file(path))

    def save(self, state: MicrocycleRevisionState) -> None:
        path = self._path_for(state.scenario_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomically(path, state.to_dict())

    def _path_for(self, scenario_id: str) -> Path:
        return self.root / "microcycle-revisions" / f"{_scenario_key(scenario_id)}.json"


def managed_working_ref(scenario_id: str) -> str:
    if not scenario_id or len(scenario_id) > 128:
        raise ValueError("scenario id must be between 1 and 128 characters")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in scenario_id):
        raise ValueError("scenario id contains unsafe ref characters")
    return f"refs/heads/athba/microcycles/{_scenario_key(scenario_id)}"


def _scenario_key(scenario_id: str) -> str:
    return sha256(scenario_id.encode("utf-8")).hexdigest()