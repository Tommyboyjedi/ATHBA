"""ATHBA-owned lifecycle for generated development projects and runtimes."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from core.development.python_test_runtime import PythonPytestRuntime
from core.execution.rack_ai_contract import RepositoryBinding


LIFECYCLE_STATES = {"created", "prepared", "ready", "retired"}


@dataclass(frozen=True)
class ProjectRuntime:
    kind: str
    version: str
    environment_path: str
    test_command: list[str]
    build_command: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "version": self.version, "environment_path": self.environment_path,
                "test_command": self.test_command, "build_command": self.build_command}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ProjectRuntime":
        return cls(str(data["kind"]), str(data["version"]), str(data["environment_path"]),
                   [str(value) for value in data["test_command"]],
                   None if data.get("build_command") is None else [str(value) for value in data["build_command"]])


@dataclass(frozen=True)
class DevelopmentProject:
    project_id: str
    repository_root: str
    default_ref: str
    trusted_base_sha: str
    runtime: ProjectRuntime
    generated_paths: list[str]
    status: str

    def __post_init__(self) -> None:
        if not self.project_id or self.status not in LIFECYCLE_STATES:
            raise ValueError("invalid project lifecycle state")

    def binding(self) -> RepositoryBinding:
        return RepositoryBinding(self.project_id, self.default_ref, self.trusted_base_sha, self.repository_root)

    def to_dict(self) -> dict[str, object]:
        return {"project_id": self.project_id, "repository_root": self.repository_root, "default_ref": self.default_ref,
                "trusted_base_sha": self.trusted_base_sha, "runtime": self.runtime.to_dict(),
                "generated_paths": self.generated_paths, "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DevelopmentProject":
        return cls(str(data["project_id"]), str(data["repository_root"]), str(data["default_ref"]),
                   str(data["trusted_base_sha"]), ProjectRuntime.from_dict(dict(data["runtime"])),
                   [str(value) for value in data.get("generated_paths", [])], str(data["status"]))


class ProjectEnvironmentRepo:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def load(self, project_id: str) -> DevelopmentProject | None:
        path = self.root / project_id / "project.json"
        return None if not path.exists() else DevelopmentProject.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def save(self, project: DevelopmentProject) -> None:
        path = self.root / project.project_id / "project.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(project.to_dict(), indent=2, sort_keys=True), encoding="utf-8")


class ProjectEnvironmentService:
    """Create, persist, reuse, and retire only ATHBA-owned project roots."""

    def __init__(self, root: str | Path, python_executable: str = "/srv/ATHBA/.venv/bin/python"):
        self.root = Path(root).resolve()
        self.repo = ProjectEnvironmentRepo(self.root)
        self.python_executable = python_executable

    def create_or_load_python_project(self, project_id: str) -> DevelopmentProject:
        existing = self.repo.load(project_id)
        if existing is not None:
            if existing.status == "retired":
                raise ValueError("retired projects cannot be reused")
            self._assert_ready(existing)
            return existing
        project_root = (self.root / project_id / "repository").resolve()
        if project_root.exists():
            raise ValueError("project root exists without persisted ATHBA project state")
        project_root.mkdir(parents=True)
        self._git(project_root, "init", "-q", "-b", "main")
        (project_root / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
        self._git(project_root, "add", ".gitignore")
        self._git(project_root, "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "ATHBA project seed")
        sha = self._git(project_root, "rev-parse", "HEAD").strip()
        runtime = PythonPytestRuntime(self.python_executable)
        project = DevelopmentProject(project_id, str(project_root), "main", sha,
            ProjectRuntime("python", "3.14", self.python_executable, runtime.pytest_command(".")),
            ["__pycache__", ".pytest_cache"], "prepared")
        self._assert_ready(project)
        project = replace(project, status="ready")
        self.repo.save(project)
        return project

    def retire(self, project_id: str, *, remove_workspace: bool = False) -> DevelopmentProject:
        project = self._required(project_id)
        if remove_workspace:
            root = Path(project.repository_root).resolve()
            if self.root not in root.parents:
                raise ValueError("refusing to remove a non-ATHBA project root")
            shutil.rmtree(root)
        retired = replace(project, status="retired")
        self.repo.save(retired)
        return retired

    def _required(self, project_id: str) -> DevelopmentProject:
        project = self.repo.load(project_id)
        if project is None:
            raise ValueError("unknown ATHBA project")
        return project

    def _assert_ready(self, project: DevelopmentProject) -> None:
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
        if not self._git(root, "rev-parse", "--verify", f"{project.trusted_base_sha}^{{commit}}").strip():
            raise ValueError("project trusted revision is unavailable")

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout
