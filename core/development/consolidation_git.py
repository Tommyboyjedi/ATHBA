"""Isolated test replacement and exact-base publication using existing Git facilities."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.development.consolidation_evidence import CaseSnapshot
from core.development.microcycle_revision_git import MicrocycleGitClient, RevisionResolveRequest
from core.development.post_behavior_git import PostBehaviorGit
from core.development.project_environment import ProjectEnvironmentService
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.test_material import TestMaterialAdapter, TestModuleReplacementRequest


@dataclass(frozen=True)
class TestReplacementInput:
    baseline: str
    previous_tests: tuple[CaseSnapshot, ...]
    replacement_source: str
    replacement_identity: str


@dataclass(frozen=True)
class ConsolidationPromotion:
    project_id: str
    baseline: str
    revision: str


class ConsolidationGit:
    """Create test-only descendants and publish only the verified accepted pair."""

    def __init__(self, repository_root: Path, material: TestMaterialAdapter):
        self.git = PostBehaviorGit(repository_root)
        self.material = material

    def create(self, request: TestReplacementInput) -> str:
        paths = {case.path for case in request.previous_tests}
        if len(paths) != 1:
            raise ValueError("consolidation supports one existing test module")
        path = next(iter(paths))
        original = self.git.command(("show", f"{request.baseline}:{path}"))
        merged = self.material.replace(TestModuleReplacementRequest(
            original, request.replacement_source, request.replacement_identity,
            tuple(case.name for case in request.previous_tests)))
        with self.git.test_workspace(request.baseline) as workspace:
            target = workspace / path
            if target.is_symlink() or workspace not in target.resolve().parents:
                raise ValueError("consolidation test target escaped candidate")
            target.write_text(merged)
            candidate = PostBehaviorGit(workspace)
            candidate.command(("add", "--", path))
            candidate.command(("-c", "user.name=ATHBA", "-c", "user.email=athba@example.test",
                "commit", "--no-verify", "-m", "ATHBA approved test-evidence replacement"))
            revision = candidate.command(("rev-parse", "HEAD")).strip()
            self.validate_test_only((request.baseline, revision), path)
            return revision

    def validate_test_only(self, revisions: tuple[str, str], path: str) -> None:
        base, candidate = revisions
        self.git.validate_candidate(revisions)
        changed = self.git.command(("diff", "--name-only", base, candidate)).splitlines()
        if set(changed) != {path}:
            raise ValueError("test consolidation changed production or unrelated paths")

    def assert_clean(self, revision: str) -> None:
        exact = self.git.command(("rev-parse", "--verify", f"{revision}^{{commit}}")).strip()
        if exact != revision:
            raise ValueError("consolidation requires an exact immutable accepted revision")
        if self.git.command(("diff-files", "--name-only")).strip():
            raise ValueError("independent worktree changes prevent consolidation publication")
        index = self.git.command(("write-tree",)).strip()
        tree = self.git.command(("rev-parse", f"{revision}^{{tree}}")).strip()
        if index != tree:
            raise ValueError("independent index changes prevent consolidation publication")

    def assert_trial_unchanged(self, workspace: Path) -> None:
        git = PostBehaviorGit(workspace)
        if git.command(("status", "--porcelain", "--untracked-files=all")).strip():
            raise ValueError("consolidation acceptance mutated immutable candidate material")

    def publish(self, request: ConsolidationPromotion, environment: ProjectEnvironmentService) -> None:
        project = environment.repo.load(request.project_id)
        if project is None or project.trusted_base_sha not in {request.baseline, request.revision}:
            raise ValueError("consolidation project authority diverged")
        client = MicrocycleGitClient(self.git.repository_root)
        current = client.resolve(RevisionResolveRequest(f"refs/heads/{project.default_ref}"))
        if current not in {request.baseline, request.revision}:
            raise ValueError("consolidation canonical authority diverged")
        index = self.git.command(("write-tree",)).strip()
        permitted = {self.git.command(("rev-parse", f"{rev}^{{tree}}")).strip()
                     for rev in (request.baseline, request.revision)}
        if self.git.command(("diff-files", "--name-only")).strip() or index not in permitted:
            raise ValueError("independent project edits prevent consolidation publication")
        if current == request.baseline:
            environment.record_trusted_revision(request.project_id, request.revision)
        TrustedProjectRevisionSynchronizer(environment).synchronize(request.project_id, request.revision)
