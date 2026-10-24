"""Prepared project authority shared by legacy and delivery-scoped compositions."""
from __future__ import annotations

from typing import Protocol

from core.development.project_environment import DevelopmentProject, ProjectLoadDisposition
from core.development.project_environment_git import GitProjectClient


class ProjectEnvironmentRepository(Protocol):
    def load(self, project_id: str) -> DevelopmentProject | None: ...

    def save(self, project: DevelopmentProject) -> None: ...


class PreparedProjectEnvironment(Protocol):
    @property
    def repo(self) -> ProjectEnvironmentRepository: ...

    def _git_client(self) -> GitProjectClient: ...

    def create_or_load_python_project_with_disposition(
        self, project_id: str, production_paths: tuple[str, ...] = (),
    ) -> ProjectLoadDisposition: ...

    def record_trusted_revision(self, project_id: str, revision: str) -> DevelopmentProject: ...
