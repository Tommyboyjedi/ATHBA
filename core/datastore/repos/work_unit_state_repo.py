import json
import os
from pathlib import Path

from core.development.progression import CoordinationSnapshot


class WorkUnitStateRepo:
    def __init__(self, root: str | Path | None = None):
        state_root = root or os.environ.get("ATHBA_STATE_ROOT") or "state/work-unit-runs"
        self.root = Path(state_root)

    def load(self, project_id: str) -> CoordinationSnapshot | None:
        path = self._path_for(project_id)
        if not path.exists():
            return None
        return CoordinationSnapshot.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, snapshot: CoordinationSnapshot) -> Path:
        path = self._path_for(snapshot.project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def _path_for(self, project_id: str) -> Path:
        return self.root / f"{project_id}.json"
