"""Disposable-Git proofs of branch isolation, guarded publication and conflicts."""
from pathlib import Path

import pytest

from core.delivery_management.git_merge import GitMerge, MergeRequest
from core.delivery_management.git_workspaces import BranchWorkspace, GitCommand, GitWorkspaces, git
from core.delivery_management.publication import CheckedPublication, PromotionRequest


def commit(root: Path, name: str, body: str) -> str:
    (root / name).write_text(body)
    git(GitCommand(root, ("add", name)))
    git(GitCommand(root, ("-c", "user.name=Test", "-c", "user.email=test@example.test",
                          "commit", "-qm", name)))
    return git(GitCommand(root, ("rev-parse", "HEAD")))


def repository(root: Path) -> tuple[Path, str]:
    repo = root / "application"
    repo.mkdir()
    git(GitCommand(repo, ("init", "-q", "-b", "release")))
    return repo, commit(repo, "shared.txt", "accepted\n")


def test_isolated_branches_merge_candidate_cas_recovery_and_reuse(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    workspaces = GitWorkspaces()
    first = BranchWorkspace(repo, tmp_path / "branches" / "first", "refs/heads/delivery/first",
                            base, tmp_path / "branches", "refs/heads/release")
    second = BranchWorkspace(repo, tmp_path / "branches" / "second", "refs/heads/delivery/second",
                             base, tmp_path / "branches", "refs/heads/release")
    workspaces.prepare(first)
    workspaces.prepare(second)
    result = commit(first.worktree_root, "first.txt", "first\n")
    assert not (repo / "first.txt").exists()
    assert not (second.worktree_root / "first.txt").exists()
    assert workspaces.revision(repo, "refs/heads/release") == base
    merger = GitMerge()
    request = MergeRequest(repo, tmp_path / "trials" / "first", base, result, "first",
                           tmp_path / "trials")
    candidate = merger.prepare(request)
    assert candidate.revision and not candidate.conflicts
    assert workspaces.revision(repo, "refs/heads/release") == base
    publication = PromotionRequest(repo, repo, "refs/heads/release", base, candidate.revision)
    git(GitCommand(repo, ("update-ref", publication.target_ref, candidate.revision, base)))
    assert not (repo / "first.txt").exists()
    assert CheckedPublication().recover(publication) == candidate.revision
    assert (repo / "first.txt").read_text() == "first\n"
    merger.cleanup(request)
    assert not candidate.trial_root.exists()
    assert merger.prepare(request).revision == candidate.revision
    merger.cleanup(request)
    newer = commit(repo, "later.txt", "later\n")
    with pytest.raises(ValueError, match="newer|stale"):
        CheckedPublication().recover(publication)
    assert workspaces.revision(repo, "refs/heads/release") == newer


def test_conflicts_and_unsafe_or_dirty_bindings_do_not_change_live_refs(tmp_path: Path) -> None:
    repo, base = repository(tmp_path)
    workspaces = GitWorkspaces()
    binding = BranchWorkspace(repo, tmp_path / "branches" / "first", "refs/heads/delivery/first",
                              base, tmp_path / "branches", "refs/heads/release")
    workspaces.prepare(binding)
    branch = commit(binding.worktree_root, "shared.txt", "branch\n")
    main = commit(repo, "shared.txt", "main\n")
    merger = GitMerge()
    request = MergeRequest(repo, tmp_path / "trials" / "conflict", main, branch, "conflict",
                           tmp_path / "trials")
    candidate = merger.prepare(request)
    assert candidate.revision is None
    assert candidate.conflicts == ("shared.txt",)
    assert (repo / "shared.txt").read_text() == "main\n"
    assert (binding.worktree_root / "shared.txt").read_text() == "branch\n"
    assert workspaces.revision(repo, "refs/heads/release") == main
    merger.cleanup(request)
    outside = BranchWorkspace(repo, tmp_path / "outside", "refs/heads/delivery/unsafe",
                              base, tmp_path / "branches", "refs/heads/release")
    with pytest.raises(ValueError, match="outside"):
        workspaces.prepare(outside)
    (repo / "unowned.txt").write_text("must survive")
    with pytest.raises(ValueError, match="not clean|ambiguous"):
        CheckedPublication().promote(PromotionRequest(repo, repo, "refs/heads/release", main, main))
    assert (repo / "unowned.txt").read_text() == "must survive"
