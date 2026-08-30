import os
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.tdd_progression import TddSnapshot
from core.filesystem_policy import resolve_identifier_path


class TddStateRepo:
    def __init__(self, root: str | Path | None = None):
        state_root = (
            root
            or os.environ.get("ATHBA_TDD_STATE_ROOT")
            or os.environ.get("ATHBA_STATE_ROOT")
            or "state/tdd-runs"
        )
        self.root = Path(state_root).resolve()

    def load(self, project_id: str) -> TddSnapshot | None:
        path = self._path_for(project_id)
        if not path.exists():
            return None
        return TddSnapshot.from_dict(read_json_file(path))

    def save(self, snapshot: TddSnapshot) -> Path:
        path = self._path_for(snapshot.project_id)
        write_json_atomically(path, snapshot.to_dict())
        return path

    def _path_for(self, project_id: str) -> Path:
        return resolve_identifier_path(self.root, project_id, "project id").with_suffix(".json")
