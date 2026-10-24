"""A delivery-scoped view of one real parent environment; never a second project."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService, ProjectLoadDisposition
from core.development.project_environment_git import GitProjectClient
from core.delivery_management.domain import TeamDelivery
from core.delivery_management.git_workspaces import BranchWorkspace, GitCommand, GitWorkspaces, git
from core.delivery_management.publication import CheckedPublication, PromotionRequest, checkout_matches
from core.delivery_management.store import ManagementStore, RecordIdentity


@dataclass(frozen=True)
class BranchEnvironmentBinding:
    parent: ProjectEnvironmentService
    records: ManagementStore
    identity: RecordIdentity


class BranchProjectRepository:
    def __init__(self, binding: BranchEnvironmentBinding):
        self.binding = binding

    def load(self, project_id: str) -> DevelopmentProject | None:
        record = self.binding.records.delivery(self.binding.identity)
        if record is None or record.project_id != project_id:
            return None
        parent = self.binding.parent.repo.load(project_id)
        if parent is None:
            raise ValueError("delivery requires its existing parent environment")
        return replace(parent, repository_root=record.worktree,
                       default_ref=record.branch_ref.removeprefix("refs/heads/"),
                       trusted_base_sha=record.trusted_revision)

    def save(self, project: DevelopmentProject) -> None:
        current = self.load(project.project_id)
        _require_branch(self.binding)
        if current is None or replace(project, trusted_base_sha=current.trusted_base_sha) != current:
            raise ValueError("delivery cannot replace project/runtime/workspace authority")
        if git(GitCommand(Path(project.repository_root), ("rev-parse", "HEAD"))) != project.trusted_base_sha:
            raise ValueError("delivery metadata must match its actual branch revision")
        GitWorkspaces().require_clean(Path(project.repository_root))
        git(GitCommand(Path(project.repository_root), ("merge-base", "--is-ancestor",
            current.trusted_base_sha, project.trusted_base_sha)))
        def update(record: TeamDelivery) -> TeamDelivery:
            if record.trusted_revision != current.trusted_base_sha:
                raise ValueError("delivery trusted revision changed during synchronization")
            return replace(record, trusted_revision=project.trusted_base_sha, revision_intent=None)
        self.binding.records.update_delivery((self.binding.identity, update))


class BranchEnvironment:
    def __init__(self, binding: BranchEnvironmentBinding):
        self.binding = binding
        self.repo = BranchProjectRepository(binding)

    def create_or_load_python_project_with_disposition(
        self, project_id: str, production_paths: tuple[str, ...] = (),
    ) -> ProjectLoadDisposition:
        project = self.recover_behavioral_checkpoint()
        if project.project_id != project_id:
            raise ValueError("delivery workspace must be prepared before BDE admission")
        record = self.binding.records.delivery(self.binding.identity)
        parent = self.binding.parent.repo.load(project_id)
        assert record is not None and parent is not None
        GitWorkspaces().verify(BranchWorkspace(Path(parent.repository_root), Path(record.worktree),
            record.branch_ref, record.fork_revision, Path(record.worktree).parent,
            "refs/heads/" + parent.default_ref))
        if git(GitCommand(Path(project.repository_root), ("rev-parse", "HEAD"))) != project.trusted_base_sha:
            raise ValueError("delivery branch differs from its trusted checkpoint")
        return ProjectLoadDisposition(project, False)

    def record_trusted_revision(self, project_id: str, revision: str) -> DevelopmentProject:
        project = self.repo.load(project_id)
        parent = self.binding.parent.repo.load(project_id)
        if project is None or parent is None:
            raise ValueError("unknown delivery project")
        self.binding.records.update_delivery((self.binding.identity, lambda value: replace(
            value, revision_intent=(project.trusted_base_sha, revision))))
        CheckedPublication().promote(PromotionRequest(
            Path(parent.repository_root), Path(project.repository_root), "refs/heads/" + project.default_ref,
            project.trusted_base_sha, revision))
        updated = replace(project, trusted_base_sha=revision)
        self.repo.save(updated)
        return updated

    def recover_trusted_revision(self) -> DevelopmentProject:
        record = self.binding.records.delivery(self.binding.identity)
        project = self.repo.load(self.binding.identity.project_id)
        parent = self.binding.parent.repo.load(self.binding.identity.project_id)
        if record is None or project is None or parent is None or record.revision_intent is None:
            raise ValueError("delivery has no journaled branch publication to recover")
        old, candidate = record.revision_intent
        if project.trusted_base_sha not in {old, candidate}:
            raise ValueError("branch recovery refuses newer delivery metadata")
        actual = git(GitCommand(Path(project.repository_root), ("rev-parse", record.branch_ref)))
        if actual == old and checkout_matches(Path(project.repository_root), old):
            self.binding.records.update_delivery((self.binding.identity,
                lambda value: replace(value, revision_intent=None)))
            return project
        CheckedPublication().recover(PromotionRequest(Path(parent.repository_root),
            Path(project.repository_root), record.branch_ref, old, candidate))
        updated = replace(project, trusted_base_sha=candidate)
        self.repo.save(updated)
        return updated

    def recover_behavioral_checkpoint(self) -> DevelopmentProject:
        from core.delivery_management.bde_checkpoint_recovery import recover_accepted_checkpoint
        _require_branch(self.binding)
        return recover_accepted_checkpoint(self)

    def _git_client(self) -> GitProjectClient:
        return GitProjectClient(self._run)

    def _run(self, root: Path, *arguments: str) -> str:
        _require_branch(self.binding)
        project = self.repo.load(self.binding.identity.project_id)
        if project is None or root.resolve() != Path(project.repository_root).resolve():
            raise ValueError("delivery Git operation targets a different workspace")
        if arguments and arguments[0] == "update-ref":
            if len(arguments) < 2 or arguments[1] != "refs/heads/" + project.default_ref:
                raise ValueError("delivery environment cannot promote another branch")
        if arguments[:3] == ("read-tree", "--reset", "-u"):
            revision = arguments[3]
            if checkout_matches(root, revision):
                return ""
            if not checkout_matches(root, project.trusted_base_sha):
                raise ValueError("delivery checkout contains unowned changes")
            return git(GitCommand(root, ("read-tree", "-m", "-u", project.trusted_base_sha, revision)))
        return git(GitCommand(root, tuple(arguments)))


def _require_branch(binding: BranchEnvironmentBinding) -> None:
    from core.delivery_management.git_workspaces import common_directory
    record = binding.records.delivery(binding.identity)
    parent = binding.parent.repo.load(binding.identity.project_id)
    if record is None or parent is None:
        raise ValueError("unknown delivery workspace authority")
    root = Path(record.worktree)
    if (root.is_symlink() or (root / ".git").is_symlink()
            or common_directory(root) != common_directory(Path(parent.repository_root))
            or git(GitCommand(root, ("symbolic-ref", "HEAD"))) != record.branch_ref):
        raise ValueError("delivery workspace switched branch or repository")
