"""File-backed persistence for ATHBA project state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.atomic_json_file import read_json_file, write_json_atomically
from core.development.project_environment_state import DevelopmentProject
from core.filesystem_policy import resolve_identifier_path


@dataclass
class ProjectEnvironmentRepo:
    root: Path

    def __init__(self, root: str | Path):
        object.__setattr__(self, "root", Path(root).resolve())

    def load(self, project_id: str) -> DevelopmentProject | None:
        path = self._path_for(project_id)
        if not path.exists():
            return None
        return DevelopmentProject.from_dict(read_json_file(path))

    def save(self, project: DevelopmentProject) -> None:
        write_json_atomically(self._path_for(project.project_id), project.to_dict())

    def _path_for(self, project_id: str) -> Path:
        return resolve_identifier_path(self.root, project_id, "project id") / "project.json"
