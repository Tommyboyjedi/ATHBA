"""Filesystem persistence for isolated scenario-drafting state."""
from __future__ import annotations

import os
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.scenario_drafting_domain import ScenarioDraftRunState
from core.filesystem_policy import resolve_identifier_path


class ScenarioDraftStateRepo:
    def __init__(self, root: str | Path | None = None):
        state_root = (
            root
            or os.environ.get("ATHBA_SCENARIO_DRAFT_STATE_ROOT")
            or os.environ.get("ATHBA_STATE_ROOT")
            or "state/scenario-drafts"
        )
        self.root = Path(state_root).resolve()

    def load(self, scenario_id: str) -> ScenarioDraftRunState | None:
        path = self._path_for(scenario_id)
        if not path.exists():
            return None
        return ScenarioDraftRunState.from_dict(read_json_file(path))

    def save(self, state: ScenarioDraftRunState) -> Path:
        path = self._path_for(state.scenario_id)
        write_json_atomically(path, state.to_dict())
        return path

    def _path_for(self, scenario_id: str) -> Path:
        return resolve_identifier_path(self.root, scenario_id, "scenario id").with_suffix(".json")
