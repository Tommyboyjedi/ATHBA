"""Exact compare-and-swap publication with recoverable managed checkout updates."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from core.development.project_environment_git import GitProjectClient, RefPromotionRequest
from core.delivery_management.git_workspaces import (
    GitCommand, GitWorkspaces, common_directory, git, require_commit, safe_directory, verify_linked_repository,
)


@dataclass(frozen=True)
class PromotionRequest:
    canonical_root: Path
    target_root: Path
    target_ref: str
    expected_revision: str
    candidate_revision: str


@contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    path = common_directory(root) / "athba-publication.lock"
    if path.is_symlink():
        raise ValueError("publication lock cannot be a symlink")
    with path.open("a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def checkout_matches(root: Path, revision: str) -> bool:
    tree = git(GitCommand(root, ("rev-parse", f"{revision}^{{tree}}")))
    if git(GitCommand(root, ("write-tree",))) != tree:
        return False
    if git(GitCommand(root, ("diff-files", "--name-only"))):
        return False
    return not git(GitCommand(root, ("ls-files", "--others", "--exclude-standard")))


class CheckedPublication:
    """Caller must durably journal exact approval before entering publication."""

    def promote(self, request: PromotionRequest) -> str:
        self._binding(request)
        with publication_lock(request.canonical_root):
            self._binding(request)
            current = git(GitCommand(request.canonical_root, ("rev-parse", request.target_ref)))
            if current == request.candidate_revision:
                self._synchronize(request)
                return current
            if current != request.expected_revision:
                raise ValueError("stale publication: authoritative target revision changed")
            GitWorkspaces().require_clean(request.target_root)
            if not checkout_matches(request.target_root, request.expected_revision):
                raise ValueError("target checkout does not match pinned accepted revision")
            git(GitCommand(request.canonical_root, ("merge-base", "--is-ancestor",
                                                   request.expected_revision, request.candidate_revision)))
            client = GitProjectClient(lambda root, *args: git(GitCommand(root, args)))
            client.promote(RefPromotionRequest(request.canonical_root, request.target_ref,
                                               request.expected_revision, request.candidate_revision))
            self._synchronize(request)
            return request.candidate_revision

    def recover(self, request: PromotionRequest) -> str:
        self._binding(request)
        with publication_lock(request.canonical_root):
            self._binding(request)
            current = git(GitCommand(request.canonical_root, ("rev-parse", request.target_ref)))
            if current != request.candidate_revision:
                raise ValueError("publication recovery refuses an absent or newer target revision")
            self._synchronize(request)
            return current

    def _binding(self, request: PromotionRequest) -> None:
        canonical = safe_directory(request.canonical_root)
        target = safe_directory(request.target_root)
        if (canonical / ".git").is_symlink() or not (canonical / ".git").is_dir() or common_directory(target) != common_directory(canonical):
            raise ValueError("publication target belongs to another repository")
        if target != canonical:
            verify_linked_repository(canonical, target)
        if not request.target_ref.startswith("refs/heads/"):
            raise ValueError("publication requires an explicit local branch")
        git(GitCommand(canonical, ("check-ref-format", request.target_ref)))
        if git(GitCommand(target, ("symbolic-ref", "-q", "HEAD"))) != request.target_ref:
            raise ValueError("publication target checkout is on another branch")
        listed = git(GitCommand(canonical, ("worktree", "list", "--porcelain")))
        if f"worktree {target}\n" not in listed + "\n":
            raise ValueError("publication target is not a registered managed worktree")
        require_commit(canonical, request.expected_revision)
        require_commit(canonical, request.candidate_revision)
        git(GitCommand(canonical, ("merge-base", "--is-ancestor",
                                  request.expected_revision, request.candidate_revision)))

    def _synchronize(self, request: PromotionRequest) -> None:
        root = request.target_root
        if checkout_matches(root, request.candidate_revision):
            return
        if not checkout_matches(root, request.expected_revision):
            raise ValueError("publication checkout has unowned or ambiguous changes; recovery is blocked")
        git(GitCommand(root, ("read-tree", "-m", "-u", request.expected_revision, request.candidate_revision)))
        if not checkout_matches(root, request.candidate_revision):
            raise RuntimeError("publication checkout synchronization is incomplete")
