"""Filesystem persistence for strict TDD microcycle progress."""
from __future__ import annotations

import os
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.microcycle_domain import MicrocycleState
from core.filesystem_policy import resolve_identifier_path


class MicrocycleStateRepo:
    """Stores independently resumable strict-microcycle state."""

    def __init__(self, root: str | Path | None = None):
        state_root = (
            root
            or os.environ.get("ATHBA_MICROCYCLE_STATE_ROOT")
            or os.environ.get("ATHBA_STATE_ROOT")
            or "state/microcycles"
        )
        self.root = Path(state_root).resolve()

    def load(self, scenario_id: str) -> MicrocycleState | None:
        path = self._path_for(scenario_id)
        if not path.exists():
            return None
        return MicrocycleState.from_dict(read_json_file(path))

    def save(self, state: MicrocycleState) -> Path:
        path = self._path_for(state.scenario_draft.scenario_id)
        write_json_atomically(path, state.to_dict())
        return path

    def _path_for(self, scenario_id: str) -> Path:
        return resolve_identifier_path(self.root, scenario_id, "scenario id").with_suffix(".json")
