"""File-backed persistence for ATHBA project state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.development.project_environment_state import DevelopmentProject


@dataclass
class ProjectEnvironmentRepo:
    root: Path

    def __init__(self, root: str | Path):
        object.__setattr__(self, "root", Path(root))

    def load(self, project_id: str) -> DevelopmentProject | None:
        path = self.root / project_id / "project.json"
        if not path.exists():
            return None
        return DevelopmentProject.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, project: DevelopmentProject) -> None:
        path = self.root / project.project_id / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(project.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
