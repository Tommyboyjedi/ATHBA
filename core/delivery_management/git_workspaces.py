"""Verified linked-worktree bindings for independent behavior deliveries."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path



@dataclass(frozen=True)
class BranchWorkspace:
    canonical_root: Path
    worktree_root: Path
    branch_ref: str
    fork_revision: str
    owned_root: Path
    canonical_ref: str


@dataclass(frozen=True)
class GitCommand:
    root: Path
    arguments: tuple[str, ...]


GIT_COMMAND_TIMEOUT_SECONDS = 30


def git(command: GitCommand) -> str:
    return subprocess.run(
        ("git", *command.arguments), cwd=command.root, check=True,
        capture_output=True, text=True, timeout=GIT_COMMAND_TIMEOUT_SECONDS,
    ).stdout.strip()


def safe_directory(path: Path) -> Path:
    absolute = path.absolute()
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise ValueError("managed Git paths cannot contain symlinks")
    return absolute.resolve()


def require_owned(path: Path, owned_root: Path) -> Path:
    root = safe_directory(owned_root)
    target = safe_directory(path)
    if target == root or root not in target.parents:
        raise ValueError("worktree is outside its explicit owned root")
    return target


def common_directory(root: Path) -> Path:
    return Path(git(GitCommand(root, ("rev-parse", "--path-format=absolute", "--git-common-dir")))).resolve()


def verify_linked_repository(canonical: Path, target: Path) -> None:
    pointer = target / ".git"
    if not pointer.is_file() or pointer.is_symlink():
        raise ValueError("delivery workspace must be a registered linked worktree")
    if common_directory(target) != common_directory(canonical):
        raise ValueError("delivery workspace belongs to another repository")
    git_dir = Path(git(GitCommand(target, ("rev-parse", "--absolute-git-dir"))))
    reciprocal = git_dir / "gitdir"
    if safe_directory(git_dir).parent != common_directory(canonical) / "worktrees":
        raise ValueError("linked Git directory is outside canonical worktree registrations")
    if not reciprocal.is_file() or reciprocal.is_symlink() or reciprocal.read_text().strip() != str(pointer):
        raise ValueError("linked Git pointer lacks reciprocal ownership")
    listed = git(GitCommand(canonical, ("worktree", "list", "--porcelain")))
    if f"worktree {target}\n" not in listed + "\n":
        raise ValueError("linked worktree is not registered by the canonical repository")


def require_commit(root: Path, revision: str) -> str:
    actual = git(GitCommand(root, ("rev-parse", "--verify", f"{revision}^{{commit}}")))
    if actual != revision:
        raise ValueError("revision must be an exact commit identity")
    return actual


class GitWorkspaces:
    def prepare(self, binding: BranchWorkspace) -> BranchWorkspace:
        canonical = self._canonical(binding)
        target = require_owned(binding.worktree_root, binding.owned_root)
        if canonical in target.parents or common_directory(canonical) == target:
            raise ValueError("delivery worktree cannot be inside the application checkout")
        require_commit(canonical, binding.fork_revision)
        self.require_clean(canonical)
        if target.exists():
            self.verify(binding)
            return binding
        try:
            prior = self.revision(canonical, binding.branch_ref)
        except subprocess.CalledProcessError:
            prior = None
        if prior is not None:
            raise ValueError("delivery branch exists without the owned worktree")
        target.parent.mkdir(parents=True, exist_ok=True)
        git(GitCommand(canonical, ("worktree", "add", "-b", binding.branch_ref.removeprefix("refs/heads/"),
                                  str(target), binding.fork_revision)))
        self.verify(binding)
        return binding

    def verify(self, binding: BranchWorkspace) -> BranchWorkspace:
        canonical = self._canonical(binding)
        target = require_owned(binding.worktree_root, binding.owned_root)
        verify_linked_repository(canonical, target)
        if git(GitCommand(target, ("symbolic-ref", "-q", "HEAD"))) != binding.branch_ref:
            raise ValueError("delivery checkout is bound to another branch")
        require_commit(canonical, binding.fork_revision)
        self.require_clean(target)
        return binding

    def revision(self, root: Path, ref: str) -> str:
        return git(GitCommand(root, ("rev-parse", "--verify", f"{ref}^{{commit}}")))

    def require_clean(self, root: Path) -> None:
        if git(GitCommand(root, ("status", "--porcelain", "--untracked-files=all"))):
            raise ValueError("managed Git checkout is not clean")
        if git(GitCommand(root, ("rev-parse", "--is-inside-work-tree"))) != "true":
            raise ValueError("managed Git root is not a worktree")

    def _canonical(self, binding: BranchWorkspace) -> Path:
        canonical = safe_directory(binding.canonical_root)
        if (canonical / ".git").is_symlink() or not (canonical / ".git").is_dir():
            raise ValueError("canonical repository must own its Git directory")
        if not binding.canonical_ref.startswith("refs/heads/"):
            raise ValueError("application canonical branch must be explicit")
        if not binding.branch_ref.startswith("refs/heads/") or binding.branch_ref == binding.canonical_ref:
            raise ValueError("delivery branch must differ from application main")
        git(GitCommand(canonical, ("check-ref-format", binding.branch_ref)))
        return canonical
