"""Read immutable candidate trees and CAS-promote independently validated revisions."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import subprocess
import tempfile

from core.development.post_behavior_domain import PostBehaviorState
from core.development.specification_evidence_policy import SpecificationSnapshot
from core.development.microcycle_revision_git import (
    MicrocycleGitClient, RevisionAncestryRequest, RevisionResolveRequest,
)
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.project_environment import ProjectEnvironmentService
from core.development.specification_revision_snapshot import GitSpecificationSnapshot

GIT_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class PostBehaviorGit:
    repository_root: Path

    def command(self, args: tuple[str, ...]) -> str:
        return subprocess.run(("git", *args), cwd=self.repository_root, check=True,
                              capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS).stdout

    def snapshot(self, revision: str) -> SpecificationSnapshot:
        snapshot = GitSpecificationSnapshot(self.repository_root).read(revision)
        if not snapshot.complete or snapshot.revision != revision:
            raise ValueError("post-behavior requires a complete exact Git snapshot")
        return snapshot

    def validate_candidate(self, revisions: tuple[str, str]) -> None:
        base, candidate = revisions
        git = MicrocycleGitClient(self.repository_root)
        if candidate == base or not git.is_ancestor(RevisionAncestryRequest(base, candidate)):
            raise ValueError("candidate must advance the exact accepted base")
        old = self._modes(base)
        new = self._modes(candidate)
        if old.keys() != new.keys() or any(new[path] != mode for path, mode in old.items()):
            raise ValueError("post-behavior candidate may not change paths or Git entry modes")

    def _modes(self, revision: str) -> dict[str, str]:
        entries = self.command(("ls-tree", "-rz", revision)).split("\0")
        return {entry.split("\t", 1)[1]: entry.split()[0] for entry in entries if entry}

    @contextmanager
    def test_workspace(self, revision: str):
        with tempfile.TemporaryDirectory(prefix="athba-post-validation-") as temporary:
            worktree = Path(temporary) / "candidate"
            self.command(("worktree", "add", "--detach", str(worktree), revision))
            try:
                yield worktree
            finally:
                self.command(("worktree", "remove", "--force", str(worktree)))


@dataclass(frozen=True)
class PostBehaviorPromotion:
    environment: ProjectEnvironmentService
    git: PostBehaviorGit

    async def promote_candidate(self, state: PostBehaviorState) -> tuple[str, ...]:
        active = state.active_pass
        if active is None or active.candidate is None or active.candidate.revision is None:
            raise ValueError("promotion requires a validated candidate")
        candidate = active.candidate.revision
        if any(item is None or not item.passed or item.revision != candidate
               for item in (active.tests, active.gatekeeper)):
            raise ValueError("promotion requires tests and Gatekeeper at candidate SHA")
        project = self.environment.repo.load(state.entry.delivery_id)
        if project is None:
            raise ValueError("post-behavior project is unavailable")
        canonical = f"refs/heads/{project.default_ref}"
        client = MicrocycleGitClient(self.git.repository_root)
        current = client.resolve(RevisionResolveRequest(canonical))
        index_tree = self.git.command(("write-tree",)).strip()
        permitted_trees = {self.git.command(("rev-parse", f"{revision}^{{tree}}")).strip()
                           for revision in (active.base_revision, candidate)}
        if self.git.command(("diff-files", "--name-only")).strip() or index_tree not in permitted_trees:
            raise ValueError("independent project worktree edits prevent trusted promotion")
        if current == active.base_revision:
            self.git.validate_candidate((active.base_revision, candidate))
            self.git.command(("update-ref", canonical, candidate, active.base_revision))
        elif current != candidate:
            raise ValueError("canonical revision diverged during post-behavior promotion")
        if project.trusted_base_sha not in {active.base_revision, candidate}:
            raise ValueError("project trusted revision diverged during promotion")
        TrustedProjectRevisionSynchronizer(self.environment).synchronize(project.project_id, candidate)
        return (f"git-promotion:{active.base_revision}:{candidate}",)
