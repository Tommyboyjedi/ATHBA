"""Bounded immutable Git access and isolated production-only trial workspaces."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import time
from typing import Callable, Iterator

from core.development.production_reduction_domain import (
    ProductionReductionRequest, ReductionDeadlineReached,
)
from core.development.production_reduction_syntax import ReductionOpportunity, ReductionSource

GIT_COMMAND_LIMIT = 15.0
CLEANUP_LIMIT = 5.0
REGULAR_MODES = {"100644", "100755"}


@dataclass(frozen=True)
class BoundedReductionGit:
    root: Path
    deadline: float

    def run(self, args: tuple[str, ...]) -> bytes:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ReductionDeadlineReached("reduction deadline reached")
        try:
            result = subprocess.run(("git", *args), cwd=self.root, capture_output=True,
                                    timeout=min(GIT_COMMAND_LIMIT, remaining), check=False)
        except subprocess.TimeoutExpired as error:
            raise ReductionDeadlineReached("reduction Git deadline reached") from error
        if result.returncode:
            raise ValueError(result.stderr.decode(errors="replace").strip())
        return result.stdout

    def entries(self, revision: str) -> dict[str, tuple[str, str]]:
        result = {}
        for entry in self.run(("ls-tree", "-rz", revision)).split(b"\0"):
            if entry:
                facts, path = entry.split(b"\t", 1)
                mode, kind, sha = facts.decode().split()
                result[path.decode()] = (mode, sha)
        return result

    def source(self, value: tuple[str, str]) -> bytes | None:
        revision, path = value
        entries = self.entries(revision)
        if path not in entries:
            return None
        if entries[path][0] not in REGULAR_MODES:
            raise ValueError("reduction cannot edit a non-regular Git entry")
        return self.run(("show", f"{revision}:{path}"))


class ReductionRepository:
    """Keeps test/config trees fixed and records descendants of the source candidate."""

    def __init__(self, request: ProductionReductionRequest, deadline: float):
        self.request = request
        self.cleanup_deadline = deadline
        remaining = max(0.0, deadline - time.monotonic())
        reserve = min(CLEANUP_LIMIT, remaining / 10)
        self.git = BoundedReductionGit(request.repository_root.resolve(), deadline - reserve)

    def validate(self, revision: str) -> None:
        request = self.request
        revisions = (request.baseline_revision, request.accepted_red_revision,
                     request.developer_input_revision, request.candidate_revision, revision)
        for value in revisions:
            if self.git.run(("rev-parse", "--verify", f"{value}^{{commit}}")).decode().strip() != value:
                raise ValueError("reduction requires exact immutable commit identities")
        for before, after in zip(revisions, revisions[1:]):
            self.git.run(("merge-base", "--is-ancestor", before, after))
        allowed = set(request.production_paths)
        if not set(request.required_artifacts).issubset(allowed):
            raise ValueError("reduction artifacts must belong to permitted production paths")
        for path in allowed:
            pure = PurePosixPath(path)
            if pure.is_absolute() or ".." in pure.parts or str(pure) != path:
                raise ValueError("unsafe reduction production path")
        if not allowed:
            raise ValueError("reduction requires explicit production paths")
        fixed = self.git.entries(request.accepted_red_revision)
        candidate = self.git.entries(revision)
        if {k: v for k, v in fixed.items() if k not in allowed} != {
                k: v for k, v in candidate.items() if k not in allowed}:
            raise ValueError("reduction candidate changed immutable tests or configuration")
        if any(path not in candidate for path in request.required_artifacts):
            raise ValueError("reduction removed a required artifact")
        for tree in (fixed, candidate, self.git.entries(request.baseline_revision)):
            if any(tree[p][0] not in REGULAR_MODES for p in allowed if p in tree):
                raise ValueError("unsupported reduction production entry mode")

    def sources(self, revision: str) -> tuple[ReductionSource, ...]:
        return tuple(ReductionSource(
            path, self.git.source((self.request.baseline_revision, path)),
            self.git.source((revision, path))) for path in self.request.production_paths)

    @contextmanager
    def trial(self, item: tuple[str, ReductionOpportunity],
              on_created: Callable[[Path], None]) -> Iterator[Path]:
        revision, opportunity = item
        with tempfile.TemporaryDirectory(prefix="athba-reduction-") as temporary:
            worktree = Path(temporary) / "candidate"
            on_created(worktree)
            try:
                self.git.run(("worktree", "add", "--detach", str(worktree), revision))
                target = worktree / opportunity.path
                if target.is_symlink() or worktree not in target.resolve().parents:
                    raise ValueError("reduction target escapes workspace")
                if opportunity.replacement is None:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(opportunity.replacement)
                yield worktree
            finally:
                if worktree.exists():
                    _cleanup_workspace((self.git.root, worktree), self.cleanup_deadline)

    def recover_trials(self, root: Path) -> None:
        _recover_trials((self.git.root, root), self.cleanup_deadline)

    def snapshot(self, worktree: Path) -> str:
        git = BoundedReductionGit(worktree, self.git.deadline)
        git.run(("add", "--", *self.request.production_paths))
        return git.run(("write-tree",)).decode().strip()

    def retain(self, item: tuple[Path, str]) -> str:
        worktree, expected_tree = item
        git = BoundedReductionGit(worktree, self.git.deadline)
        if git.run(("write-tree",)).decode().strip() != expected_tree:
            raise ValueError("trial index changed after acceptance")
        if git.run(("diff-files", "--name-only")).strip():
            raise ValueError("trial worktree changed after acceptance")
        git.run(("-c", "user.name=ATHBA", "-c", "user.email=athba@example.test",
                 "commit", "--no-verify", "-m", "ATHBA verified production-change reduction"))
        return git.run(("rev-parse", "HEAD")).decode().strip()


def opportunity_digest(value: tuple[tuple[ReductionSource, ...], ReductionOpportunity]) -> str:
    sources, opportunity = value
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.path):
        content = opportunity.replacement if source.path == opportunity.path else source.candidate
        digest.update(source.path.encode() + b"\0")
        digest.update(b"deleted" if content is None else b"blob:" + hashlib.sha256(content).digest())
    return digest.hexdigest()


def _cleanup_workspace(paths: tuple[Path, Path], deadline: float) -> None:
    repository, worktree = paths
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("reduction cleanup deadline exhausted")
    result = subprocess.run(("git", "worktree", "remove", "--force", str(worktree)),
                            cwd=repository, capture_output=True,
                            timeout=min(CLEANUP_LIMIT, remaining))
    if result.returncode:
        raise ValueError("reduction worktree cleanup failed: " +
                         result.stderr.decode(errors="replace").strip())


def _recover_trials(paths: tuple[Path, Path], deadline: float) -> None:
    repository, journal_root = paths
    git = BoundedReductionGit(repository, deadline)
    registered = git.run(("worktree", "list", "--porcelain")).decode().splitlines()
    roots = {line.removeprefix("worktree ") for line in registered if line.startswith("worktree ")}
    for record in sorted(journal_root.glob("trial-*.json")):
        item = json.loads(record.read_text())
        if "workspace" not in item or item.get("cleanup_confirmed"):
            continue
        workspace = Path(item["workspace"]).resolve()
        if (workspace.name != "candidate" or not workspace.parent.name.startswith("athba-reduction-")
                or workspace.parent.parent != Path(tempfile.gettempdir()).resolve()):
            raise ValueError("untrusted interrupted reduction workspace")
        if str(workspace) in roots:
            _cleanup_workspace((repository, workspace), deadline)
        elif workspace.exists():
            raise ValueError("interrupted reduction workspace lost Git ownership")
        if item.get("decision") == "pending":
            item["decision"] = "discarded_interrupted"
        item["cleanup_confirmed"] = True
        from core.atomic_json_file import write_json_atomically
        write_json_atomically(record, item)
