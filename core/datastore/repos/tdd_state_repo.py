import json
import os
from pathlib import Path

from core.development.tdd_progression import TddSnapshot


class TddStateRepo:
    def __init__(self, root: str | Path | None = None):
        state_root = (
            root
            or os.environ.get("ATHBA_TDD_STATE_ROOT")
            or os.environ.get("ATHBA_STATE_ROOT")
            or "state/tdd-runs"
        )
        self.root = Path(state_root)

    def load(self, project_id: str) -> TddSnapshot | None:
        path = self._path_for(project_id)
        if not path.exists():
            return None
        return TddSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, snapshot: TddSnapshot) -> Path:
        path = self._path_for(snapshot.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _path_for(self, project_id: str) -> Path:
        return self.root / f"{project_id}.json"
