"""Synchronize project metadata after the strict revision lifecycle owns canonical promotion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService
from core.development.project_environment_git import AncestryCheckRequest, CanonicalRefRequest, WorktreeSynchronisationRequest


@dataclass(frozen=True)
class TrustedProjectRevisionSynchronizer:
    """Persist a lifecycle-promoted canonical SHA without performing another ref mutation."""

    environment: ProjectEnvironmentService

    def synchronize(self, project_id: str, revision: str) -> DevelopmentProject:
        project = self._project(project_id)
        git = self.environment._git_client()
        root = Path(project.repository_root)
        canonical = git.canonical_revision(CanonicalRefRequest(root, f"refs/heads/{project.default_ref}"))
        if canonical != revision:
            raise ValueError("canonical ref does not match lifecycle-promoted revision")
        if not git.is_ancestor(AncestryCheckRequest(root, project.trusted_base_sha, revision)):
            raise ValueError("trusted revision synchronization must be fast-forward")
        updated = replace(project, trusted_base_sha=revision)
        git.synchronise_worktree(WorktreeSynchronisationRequest(root, revision))
        self.environment.repo.save(updated)
        return updated

    def _project(self, project_id: str) -> DevelopmentProject:
        project = self.environment.repo.load(project_id)
        if project is None:
            raise ValueError("unknown project cannot synchronize revision")
        return project
