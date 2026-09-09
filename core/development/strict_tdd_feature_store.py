"""Focused persistence for strict-TDD feature orchestration state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.filesystem_policy import resolve_identifier_path


@dataclass
class StrictTddFeatureRepository:
    root: Path

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def load(self, project_id: str) -> StrictTddFeatureState | None:
        path = self._path_for(project_id)
        if not path.exists():
            return None
        return StrictTddFeatureState.from_dict(read_json_file(path))

    def save(self, state: StrictTddFeatureState) -> None:
        write_json_atomically(self._path_for(state.project_id), state.to_dict())

    def _path_for(self, project_id: str) -> Path:
        return resolve_identifier_path(self.root, project_id, "project id").with_suffix(".json")