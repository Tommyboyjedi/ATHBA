"""ATHBA project lifecycle orchestration over small collaborators."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from core.development.project_environment_git import (
    AncestryCheckRequest,
    CanonicalRefRequest,
    CommitLookupRequest,
    GitProjectClient,
    ProjectWorkspacePaths,
    RefPromotionRequest,
)
from core.development.project_environment_state import (
    DevelopmentProject,
    EnvironmentLifetime,
    EnvironmentResource,
    ProjectLifecycleState,
    ProjectRuntime,
)
from core.development.project_environment_store import ProjectEnvironmentRepo
from core.development.python_test_runtime import PythonPytestRuntime


DEFAULT_ATHBA_PYTHON = "/srv/ATHBA/.venv/bin/python"


@dataclass(frozen=True)
class ProjectBootstrapRequest:
    project_id: str
    runtime_factory: "ProjectRuntimeFactory"
    readiness_verifier: "ProjectReadinessVerifier"
    git: GitProjectClient


@dataclass(frozen=True)
class TrustedRevisionPromotionRequest:
    project_id: str
    revision: str


@dataclass(frozen=True)
class ProjectRetirementRequest:
    project_id: str
    remove_workspace: bool = False


class ProjectRuntimeFactory:
    def __init__(self, python_executable: str):
        self.python_executable = python_executable

    def build(self) -> ProjectRuntime:
        runtime = PythonPytestRuntime(self.python_executable)
        resource = EnvironmentResource(str(Path(self.python_executable).parent.parent))
        return ProjectRuntime(
            kind="python",
            version="3.14",
            environment_path=self.python_executable,
            test_command=runtime.pytest_command("."),
            lifetime=EnvironmentLifetime.SHARED.value,
            environment_resources=[resource],
        )


class ProjectReadinessVerifier:
    def __init__(self, git: GitProjectClient):
        self.git = git

    def assert_ready(self, project: DevelopmentProject) -> None:
        root = Path(project.repository_root)
        if not root.is_dir() or not (root / ".git").exists():
            raise ValueError("project repository is not initialized")
        if not Path(project.runtime.environment_path).is_file():
            raise ValueError("ATHBA runtime executable is unavailable")
        runtime_check = subprocess.run(
            [project.runtime.environment_path, "-B", "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if runtime_check.returncode != 0:
            raise ValueError("ATHBA pytest runtime is unavailable")
        if not self.git.commit_exists(CommitLookupRequest(root, project.trusted_base_sha)):
            raise ValueError("project trusted revision is unavailable")


class ProjectBootstrapper:
    def __init__(self, root: Path, repo: ProjectEnvironmentRepo):
        self.root = root
        self.repo = repo

    def create_or_load(self, request: ProjectBootstrapRequest) -> DevelopmentProject:
        existing = self.repo.load(request.project_id)
        if existing is not None:
            if existing.status == ProjectLifecycleState.RETIRED.value:
                raise ValueError("retired projects cannot be reused")
            request.readiness_verifier.assert_ready(existing)
            return existing
        paths = _project_paths(self.root, request.project_id)
        if paths.repository_root.exists():
            raise ValueError("project root exists without persisted ATHBA project state")
        revision = request.git.initialize(paths)
        project = DevelopmentProject(
            project_id=request.project_id,
            repository_root=str(paths.repository_root),
            default_ref="main",
            trusted_base_sha=revision,
            runtime=request.runtime_factory.build(),
            generated_paths=["__pycache__", ".pytest_cache"],
            status=ProjectLifecycleState.PREPARED.value,
            workspace_lifetime=EnvironmentLifetime.DISPOSABLE.value,
        )
        request.readiness_verifier.assert_ready(project)
        ready = replace(project, status=ProjectLifecycleState.READY.value)
        self.repo.save(ready)
        return ready


class TrustedRevisionPromoter:
    def __init__(self, repo: ProjectEnvironmentRepo, git: GitProjectClient):
        self.repo = repo
        self.git = git

    def record(self, request: TrustedRevisionPromotionRequest) -> DevelopmentProject:
        if not isinstance(request.revision, str) or not request.revision.strip():
            raise ValueError("trusted revision must be non-empty")
        project = _required_project(self.repo, request.project_id)
        if project.status != ProjectLifecycleState.READY.value:
            raise ValueError("only ready projects can record a trusted revision")
        root = Path(project.repository_root)
        canonical_ref = f"refs/heads/{project.default_ref}"
        if not self.git.commit_exists(CommitLookupRequest(root, request.revision)):
            raise ValueError("project revision is unavailable")
        try:
            current_revision = self.git.canonical_revision(CanonicalRefRequest(root, canonical_ref))
        except subprocess.CalledProcessError as error:
            raise ValueError("project revision is unavailable") from error
        if current_revision != project.trusted_base_sha:
            raise ValueError("project canonical ref does not match trusted revision")
        if not self.git.is_ancestor(AncestryCheckRequest(root, current_revision, request.revision)):
            raise ValueError("trusted revision promotion must be fast-forward")
        self.git.promote(RefPromotionRequest(root, canonical_ref, current_revision, request.revision))
        if self.git.canonical_revision(CanonicalRefRequest(root, canonical_ref)) != request.revision:
            raise RuntimeError("project canonical ref promotion was not applied")
        updated = replace(project, trusted_base_sha=request.revision)
        try:
            self.repo.save(updated)
        except Exception:
            try:
                self.git.promote(RefPromotionRequest(root, canonical_ref, request.revision, current_revision))
            except subprocess.CalledProcessError as rollback_error:
                raise RuntimeError("trusted revision metadata persistence failed after canonical promotion") from rollback_error
            raise
        return updated


class ProjectRetirer:
    def __init__(self, root: Path, repo: ProjectEnvironmentRepo):
        self.root = root
        self.repo = repo

    def retire(self, request: ProjectRetirementRequest) -> DevelopmentProject:
        project = _required_project(self.repo, request.project_id)
        if request.remove_workspace:
            if project.workspace_lifetime == EnvironmentLifetime.SHARED.value:
                raise ValueError("shared project workspaces cannot be removed")
            root = Path(project.repository_root).resolve()
            if self.root not in root.parents:
                raise ValueError("refusing to remove a non-ATHBA project root")
            shutil.rmtree(root)
        retired = replace(project, status=ProjectLifecycleState.RETIRED.value)
        self.repo.save(retired)
        return retired


class ProjectEnvironmentService:
    """Create, validate, promote, and retire ATHBA-owned project state."""

    def __init__(self, root: str | Path, python_executable: str = DEFAULT_ATHBA_PYTHON):
        self.root = Path(root).resolve()
        self.repo = ProjectEnvironmentRepo(self.root)
        self.python_executable = python_executable

    def create_or_load_python_project(self, project_id: str) -> DevelopmentProject:
        request = ProjectBootstrapRequest(project_id, ProjectRuntimeFactory(self.python_executable), ProjectReadinessVerifier(self._git_client()), self._git_client())
        return ProjectBootstrapper(self.root, self.repo).create_or_load(request)

    def record_trusted_revision(self, project_id: str, revision: str) -> DevelopmentProject:
        return TrustedRevisionPromoter(self.repo, self._git_client()).record(TrustedRevisionPromotionRequest(project_id, revision))

    def retire(self, project_id: str, *, remove_workspace: bool = False) -> DevelopmentProject:
        return ProjectRetirer(self.root, self.repo).retire(ProjectRetirementRequest(project_id, remove_workspace))

    def _git_client(self) -> GitProjectClient:
        return GitProjectClient(self._git)

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _project_paths(root: Path, project_id: str) -> ProjectWorkspacePaths:
    project_root = (root / project_id).resolve()
    return ProjectWorkspacePaths(project_root=project_root, repository_root=(project_root / "repository").resolve())


def _required_project(repo: ProjectEnvironmentRepo, project_id: str) -> DevelopmentProject:
    project = repo.load(project_id)
    if project is None:
        raise ValueError("unknown ATHBA project")
    return project
