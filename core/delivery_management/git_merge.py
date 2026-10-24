"""Disposable history-preserving merge preparation, separate from acceptance."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.delivery_management.git_workspaces import (
    GIT_COMMAND_TIMEOUT_SECONDS, GitCommand, GitWorkspaces, common_directory, git, require_commit, require_owned, safe_directory, verify_linked_repository,
)


@dataclass(frozen=True)
class MergeRequest:
    canonical_root: Path
    trial_root: Path
    base_revision: str
    incoming_revision: str
    identity: str
    owned_root: Path


@dataclass(frozen=True)
class MergeCandidate:
    identity: str
    base_revision: str
    incoming_revision: str
    revision: str | None
    conflicts: tuple[str, ...]
    evidence: tuple[str, ...]
    trial_root: Path
    private_ref: str


def merge_identity(request: MergeRequest) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", request.identity):
        raise ValueError("merge trial identity is unsafe")
    return hashlib.sha256(request.identity.encode()).hexdigest()


def merge_marker(request: MergeRequest) -> Path:
    return request.trial_root.absolute().parent / f".{request.trial_root.name}.athba-merge.json"


def merge_authority(request: MergeRequest) -> dict[str, str]:
    return {
        "identity": request.identity, "canonical_root": str(request.canonical_root.resolve()),
        "trial_root": str(request.trial_root.resolve()), "base_revision": request.base_revision,
        "incoming_revision": request.incoming_revision,
    }


@dataclass(frozen=True)
class RetainedCandidate:
    root: Path
    ref: str
    revision: str


class GitMerge:
    def prepare(self, request: MergeRequest) -> MergeCandidate:
        canonical = safe_directory(request.canonical_root)
        trial = require_owned(request.trial_root, request.owned_root)
        if (canonical / ".git").is_symlink() or not (canonical / ".git").is_dir() or canonical in trial.parents:
            raise ValueError("merge trial repository binding is unsafe")
        require_commit(canonical, request.base_revision)
        require_commit(canonical, request.incoming_revision)
        identity = merge_identity(request)
        private_ref = f"refs/athba/merge-candidates/{identity}"
        marker = merge_marker(request)
        authority = merge_authority(request)
        if marker.exists():
            if marker.is_symlink() or json.loads(marker.read_text()) != authority:
                raise ValueError("merge trial identity or pinned revisions changed")
        else:
            if trial.exists():
                raise ValueError("merge trial path already exists without ownership")
            trial.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(json.dumps(authority, indent=2))
        if not trial.exists():
            try:
                start = git(GitCommand(canonical, ("rev-parse", "--verify", private_ref)))
            except subprocess.CalledProcessError:
                start = request.base_revision
            git(GitCommand(canonical, ("worktree", "add", "--detach", str(trial), start)))
        verify_linked_repository(canonical, trial)
        if git(GitCommand(trial, ("rev-parse", "--abbrev-ref", "HEAD"))) != "HEAD":
            raise ValueError("merge trial must have a detached HEAD")
        conflicts = self._conflicts(trial)
        revision = git(GitCommand(trial, ("rev-parse", "HEAD")))
        if revision == request.base_revision and not conflicts:
            GitWorkspaces().require_clean(trial)
            merged = subprocess.run(
                ("git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test",
                 "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                 "merge", "--no-ff", "--no-edit", "--no-gpg-sign", request.incoming_revision),
                cwd=trial, capture_output=True, text=True, check=False, timeout=GIT_COMMAND_TIMEOUT_SECONDS,
            )
            conflicts = self._conflicts(trial)
            if merged.returncode and not conflicts:
                raise ValueError(f"merge preparation failed: {merged.stderr.strip()}")
            revision = git(GitCommand(trial, ("rev-parse", "HEAD")))
        if conflicts:
            return MergeCandidate(request.identity, request.base_revision, request.incoming_revision,
                                  None, conflicts, ("ordinary merge conflict; live refs unchanged",), trial, private_ref)
        GitWorkspaces().require_clean(trial)
        for parent in (request.base_revision, request.incoming_revision):
            git(GitCommand(canonical, ("merge-base", "--is-ancestor", parent, revision)))
        self._retain(RetainedCandidate(canonical, private_ref, revision))
        return MergeCandidate(request.identity, request.base_revision, request.incoming_revision,
                              revision, (), ("ordinary history-preserving merge prepared; not accepted",),
                              trial, private_ref)

    def cleanup(self, request: MergeRequest) -> None:
        trial = require_owned(request.trial_root, request.owned_root)
        marker = merge_marker(request)
        if not marker.is_file() or marker.is_symlink() or json.loads(marker.read_text()) != merge_authority(request):
            raise ValueError("refusing cleanup without exact owned merge trial authority")
        if trial.exists():
            verify_linked_repository(request.canonical_root, trial)
            if git(GitCommand(trial, ("rev-parse", "--abbrev-ref", "HEAD"))) != "HEAD":
                raise ValueError("refusing cleanup of a non-disposable branch worktree")
            if self._conflicts(trial):
                git(GitCommand(trial, ("merge", "--abort")))
            GitWorkspaces().require_clean(trial)
            git(GitCommand(request.canonical_root, ("worktree", "remove", str(trial))))

    def _conflicts(self, root: Path) -> tuple[str, ...]:
        return tuple(git(GitCommand(root, ("diff", "--name-only", "--diff-filter=U"))).splitlines())

    def _retain(self, request: RetainedCandidate) -> None:
        root, ref, revision = request.root, request.ref, request.revision
        try:
            existing = git(GitCommand(root, ("rev-parse", "--verify", ref)))
        except subprocess.CalledProcessError:
            existing = ""
        if existing and existing != revision:
            raise ValueError("merge candidate identity already retains another revision")
        if not existing:
            git(GitCommand(root, ("update-ref", ref, revision, "0" * len(revision))))
