"""Atomic persistence for one typed durable strict-TDD run state."""
from __future__ import annotations

from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.strict_tdd_run_domain import StrictTddRunState
from core.filesystem_policy import resolve_identifier_path


class StrictTddRunStateRepository:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def load(self, run_id: str) -> StrictTddRunState | None:
        path = self._path_for(run_id)
        if not path.exists():
            return None
        try:
            return StrictTddRunState.from_dict(read_json_file(path))
        except (TypeError, ValueError) as error:
            raise ValueError("malformed strict TDD run state document") from error

    def save(self, state: StrictTddRunState) -> None:
        write_json_atomically(self._path_for(state.run_id), state.to_dict())

    def exists(self, run_id: str) -> bool:
        return self._path_for(run_id).exists()

    def _path_for(self, run_id: str) -> Path:
        return resolve_identifier_path(self.root, run_id, "run id").with_suffix(".json")