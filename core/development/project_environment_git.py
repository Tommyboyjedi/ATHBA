"""Git-side repository effects for ATHBA project workspaces."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from core.filesystem_policy import resolve_relative_path


SEED_BRANCH = "main"
SEED_GITIGNORE = "__pycache__/\n.pytest_cache/\n"
EMPTY_PYTHON_MODULE = '"""ATHBA initial production module."""\n'
SEED_COMMIT_MESSAGE = "ATHBA project seed"
SEED_USER_NAME = "ATHBA"
SEED_USER_EMAIL = "athba@example.test"


@dataclass(frozen=True)
class ProjectWorkspacePaths:
    project_root: Path
    repository_root: Path


@dataclass(frozen=True)
class CommitLookupRequest:
    repository_root: Path
    revision: str


@dataclass(frozen=True)
class CanonicalRefRequest:
    repository_root: Path
    canonical_ref: str


@dataclass(frozen=True)
class AncestryCheckRequest:
    repository_root: Path
    ancestor: str
    descendant: str


@dataclass(frozen=True)
class WorktreeSynchronisationRequest:
    repository_root: Path
    revision: str

@dataclass(frozen=True)
class RefPromotionRequest:
    repository_root: Path
    canonical_ref: str
    current_revision: str
    target_revision: str


class GitProjectClient:
    def __init__(self, runner: Callable[..., str]):
        self.runner = runner

    def initialize(
        self,
        paths: ProjectWorkspacePaths,
        initial_production_paths: Sequence[str] = (),
    ) -> str:
        paths.repository_root.mkdir(parents=True)
        self.run(paths.repository_root, "init", "-q", "-b", SEED_BRANCH)
        (paths.repository_root / ".gitignore").write_text(SEED_GITIGNORE, encoding="utf-8")
        seeded_paths = tuple(initial_production_paths)
        self._seed_production_modules(paths.repository_root, seeded_paths)
        self.run(paths.repository_root, "add", ".gitignore", *seeded_paths)
        self.run(
            paths.repository_root,
            "-c",
            f"user.name={SEED_USER_NAME}",
            "-c",
            f"user.email={SEED_USER_EMAIL}",
            "commit",
            "-qm",
            SEED_COMMIT_MESSAGE,
        )
        return self.run(paths.repository_root, "rev-parse", "HEAD").strip()

    @staticmethod
    def _seed_production_modules(repository_root: Path, paths: Sequence[str]) -> None:
        for relative_path in paths:
            target = resolve_relative_path(repository_root, relative_path, "production path")
            if target.exists():
                raise ValueError("initial production path already exists")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(EMPTY_PYTHON_MODULE, encoding="utf-8")

    def commit_exists(self, request: CommitLookupRequest) -> bool:
        try:
            self.run(request.repository_root, "rev-parse", "--verify", f"{request.revision}^{{commit}}")
        except subprocess.CalledProcessError:
            return False
        return True

    def canonical_revision(self, request: CanonicalRefRequest) -> str:
        return self.run(request.repository_root, "rev-parse", "--verify", f"{request.canonical_ref}^{{commit}}").strip()

    def is_ancestor(self, request: AncestryCheckRequest) -> bool:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", request.ancestor, request.descendant],
            cwd=request.repository_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0


    def synchronise_worktree(self, request: WorktreeSynchronisationRequest) -> None:
        self.run(request.repository_root, "read-tree", "--reset", "-u", request.revision)

    def promote(self, request: RefPromotionRequest) -> None:
        self.run(
            request.repository_root,
            "update-ref",
            request.canonical_ref,
            request.target_revision,
            request.current_revision,
        )

    def run(self, root: Path, *args: str) -> str:
        return self.runner(root, *args)
