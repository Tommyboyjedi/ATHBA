"""Prepare one approved project's bounded scaffold without executing BDE or models."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

from core.development.project_environment_git import (
    CanonicalRefRequest, CommitLookupRequest, GitProjectClient,
    ProjectWorkspacePaths, RefPromotionRequest, SEED_GITIGNORE,
    SEED_USER_EMAIL, SEED_USER_NAME,
)
from core.development.project_environment_state import (
    DevelopmentProject, EnvironmentLifetime, EnvironmentResource,
    ProjectLifecycleState, ProjectRuntime,
)
from core.development.project_environment_store import ProjectEnvironmentRepo
from core.filesystem_policy import resolve_identifier_path, resolve_relative_path
from core.project_setup.architecture import ArchitectureDecision, RepositoryPolicy, validate_scope
from core.project_setup.commands import CommandResult, SetupCommand, SetupCommandRunner
from core.project_setup.profile_domain import ProfileKind, ResolvedSetupProfile, SetupFile

SCAFFOLD_COMMIT_MESSAGE = "ATHBA approved project scaffold"
SMOKE_TEST_NAME = "test_environment_smoke.py"
SMOKE_TEST_SOURCE = "def test_environment_smoke():\n    assert True\n"
SMOKE_DIRECTORY_PREFIX = "setup-smoke-"


@dataclass(frozen=True)
class WorkspacePreparation:
    decision: ArchitectureDecision
    profile: ResolvedSetupProfile


@dataclass(frozen=True)
class PreparedWorkspace:
    project: DevelopmentProject
    commands: tuple[CommandResult, ...]


@dataclass(frozen=True)
class _WorkspaceContext:
    request: WorkspacePreparation
    paths: ProjectWorkspacePaths
    runtime: ProjectRuntime


@dataclass(frozen=True)
class _FilePlan:
    files: tuple[SetupFile, ...]
    production_paths: tuple[str, ...]
    test_paths: tuple[str, ...]


@dataclass(frozen=True)
class _Seed:
    revision: str
    default_ref: str
    created: bool


class WorkspacePreparationError(Exception):
    """Preserve failed setup command evidence without advancing trusted state."""

    def __init__(self, message: str, commands: tuple[CommandResult, ...] = ()):
        super().__init__(message)
        self.commands = commands


class ProjectSetupWorkspace:
    def __init__(self, root: Path, runner: SetupCommandRunner):
        self.root = root.resolve()
        self.runner = runner
        self.repo = ProjectEnvironmentRepo(self.root)
        self.authority = _WorkspaceGitAuthority(runner)

    def prepare(self, request: WorkspacePreparation) -> PreparedWorkspace:
        context = _context(self.root, request)
        plan = _file_plan(request)
        existing = self.repo.load(request.decision.project_id)
        if existing is not None:
            project = self.verify(existing.project_id)
            if project.runtime != context.runtime:
                raise ValueError("prepared project runtime conflicts with approved profile")
            _require_existing_files(context, plan)
            return PreparedWorkspace(project, ())
        seed = self.authority.seed(context)
        _validate_files(context, plan)
        if seed is None:
            revision = self.authority.git.initialize(context.paths)
            seed = _Seed(revision, "main", True)
        _write_files(context, plan)
        commands = _smoke_commands(context, self.runner)
        revision = self.authority.scaffold_revision(context, seed)
        project = DevelopmentProject(
            project_id=request.decision.project_id,
            repository_root=str(context.paths.repository_root),
            default_ref=seed.default_ref,
            trusted_base_sha=revision,
            runtime=context.runtime,
            generated_paths=list(request.profile.generated_paths),
            status=ProjectLifecycleState.READY.value,
            workspace_lifetime=EnvironmentLifetime.PROJECT_PERSISTENT.value,
        )
        canonical = f"refs/heads/{seed.default_ref}"
        if revision != seed.revision:
            self.authority.git.promote(RefPromotionRequest(
                context.paths.repository_root, canonical, seed.revision, revision))
        self.authority.verify_project(project)
        self.repo.save(project)
        return PreparedWorkspace(project, commands)

    def verify(self, project_id: str) -> DevelopmentProject:
        project = self.repo.load(project_id)
        if project is None:
            raise ValueError("unknown approved project environment")
        expected = _project_paths(self.root, project_id).repository_root
        if Path(project.repository_root) != expected:
            raise ValueError("project repository differs from its confined canonical root")
        self.authority.verify_project(project)
        return project

    def verify_regression(self, project_id: str) -> tuple[CommandResult, ...]:
        project = self.verify(project_id)
        result = self.runner.run(SetupCommand(
            tuple(project.runtime.test_command), Path(project.repository_root)))
        if result.returncode != 0:
            raise WorkspacePreparationError("accumulated project regression failed", (result,))
        return (result,)

    def verify_delivery(self, request: tuple[str, str, tuple[str, ...]]) -> DevelopmentProject:
        project_id, entry_revision, permitted_paths = request
        project = self.verify(project_id)
        root = Path(project.repository_root)
        self.authority.run(root, "merge-base", "--is-ancestor", entry_revision, project.trusted_base_sha)
        changed = self.authority.run(
            root, "diff", "--name-only", "-z", entry_revision, project.trusted_base_sha).split("\0")
        if any(path not in permitted_paths for path in changed if path):
            raise ValueError("delivery changed files outside this approved full-behavior scope")
        return project

    def current_revision(self, project_id: str) -> str | None:
        try:
            project = self.repo.load(project_id)
            expected = _project_paths(self.root, project_id).repository_root
            if project is None or Path(project.repository_root) != expected:
                return None
            return self.authority.git.canonical_revision(CanonicalRefRequest(
                expected, f"refs/heads/{project.default_ref}"))
        except (ValueError, OSError, subprocess.CalledProcessError):
            return None


class _WorkspaceGitAuthority:
    def __init__(self, runner: SetupCommandRunner):
        self.runner = runner
        self.git = GitProjectClient(self.run)

    def seed(self, context: _WorkspaceContext) -> _Seed | None:
        root = context.paths.repository_root
        decision = context.request.decision
        if not root.exists():
            if decision.repository_policy == RepositoryPolicy.EXISTING_APPROVED:
                raise ValueError("approved existing repository is unavailable")
            if decision.existing_repository is not None:
                raise ValueError("existing repository authority cannot create a new repository")
            return None
        authority = decision.existing_repository
        if authority is None or decision.repository_policy != RepositoryPolicy.EXISTING_APPROVED:
            raise ValueError("project root exists without approved persisted environment authority")
        if Path(authority.root).resolve() != root or not Path(authority.root).is_absolute():
            raise ValueError("approved existing repository must use this exact confined root")
        prefix = "refs/heads/"
        if not authority.canonical_ref.startswith(prefix):
            raise ValueError("approved repository requires a canonical branch ref")
        self.require_git(root, authority.canonical_ref)
        actual = self.git.canonical_revision(CanonicalRefRequest(root, authority.canonical_ref))
        if actual != authority.trusted_revision:
            raise ValueError("approved existing repository revision changed")
        return _Seed(actual, authority.canonical_ref[len(prefix):], False)

    def scaffold_revision(self, context: _WorkspaceContext, seed: _Seed) -> str:
        root = context.paths.repository_root
        self.run(root, "add", "--", *(item.path for item in _file_plan(context.request).files))
        tree = self.run(root, "write-tree").strip()
        if tree == self.run(root, "rev-parse", f"{seed.revision}^{{tree}}").strip():
            return seed.revision
        return self.run(
            root, "-c", f"user.name={SEED_USER_NAME}", "-c", f"user.email={SEED_USER_EMAIL}",
            "commit-tree", tree, "-p", seed.revision, "-m", SCAFFOLD_COMMIT_MESSAGE,
        ).strip()

    def verify_project(self, project: DevelopmentProject) -> None:
        if project.status != ProjectLifecycleState.READY.value:
            raise ValueError("project environment is not ready")
        root = Path(project.repository_root)
        canonical = f"refs/heads/{project.default_ref}"
        self.require_git(root, canonical)
        if not Path(project.runtime.environment_path).is_file():
            raise ValueError("approved managed runtime is unavailable")
        if not self.git.commit_exists(CommitLookupRequest(root, project.trusted_base_sha)):
            raise ValueError("trusted project revision is unavailable")
        if self.git.canonical_revision(CanonicalRefRequest(root, canonical)) != project.trusted_base_sha:
            raise ValueError("canonical revision differs from trusted project metadata")

    def require_git(self, root: Path, canonical: str) -> None:
        if not root.is_dir() or not (root / ".git").is_dir():
            raise ValueError("approved repository is not a canonical Git repository")
        self.run(root, "check-ref-format", canonical)
        if Path(self.run(root, "rev-parse", "--show-toplevel").strip()).resolve() != root:
            raise ValueError("repository root differs from canonical Git root")
        if self.run(root, "symbolic-ref", "HEAD").strip() != canonical:
            raise ValueError("canonical repository checkout must use its approved branch")
        if self.run(root, "status", "--porcelain", "--untracked-files=all").strip():
            raise ValueError("canonical project repository has unrelated changes")

    def run(self, root: Path, *args: str) -> str:
        result = self.runner.run(SetupCommand(("git", *args), root))
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode or 1, result.argv,
                                                output=result.stdout, stderr=result.stderr)
        return result.stdout


def _context(root: Path, request: WorkspacePreparation) -> _WorkspaceContext:
    paths = _project_paths(root, request.decision.project_id)
    profile = request.profile
    selected = tuple(item.tool for item in profile.tools)
    primary = next((tool for tool in selected if tool.executable == profile.primary_runtime_path), None)
    if primary is None or not Path(primary.executable).is_absolute():
        raise ValueError("profile requires one explicitly selected managed runtime")
    if request.decision.profile.name == ProfileKind.PYTHON:
        resources = [EnvironmentResource(str(Path(primary.executable).parent.parent))]
    else:
        resources = [EnvironmentResource(path) for path in dict.fromkeys(tool.executable for tool in selected)]
    runtime = ProjectRuntime(
        kind=request.decision.profile.name.value, version=primary.version,
        environment_path=primary.executable, test_command=list(profile.test_command),
        build_command=list(profile.build_command) or None,
        lifetime=EnvironmentLifetime.SHARED.value, environment_resources=resources,
    )
    return _WorkspaceContext(request, paths, runtime)


def _project_paths(root: Path, project_id: str) -> ProjectWorkspacePaths:
    project_root = resolve_identifier_path(root, project_id, "project id")
    literal = root / project_id
    if literal.is_symlink() or (literal / "repository").is_symlink():
        raise ValueError("project workspace authority cannot traverse symlinks")
    return ProjectWorkspacePaths(project_root, (project_root / "repository").resolve())


def _file_plan(request: WorkspacePreparation) -> _FilePlan:
    controlled = request.profile.files
    production = tuple(path for item in request.decision.behaviors for path in item.production_paths)
    tests = tuple(path for item in request.decision.behaviors for path in item.test_paths)
    names = tuple(item.path for item in controlled)
    if len(names) != len(set(names)):
        raise ValueError("profile repeats a scaffold file")
    planned = controlled + tuple(SetupFile(path, "") for path in production if path not in names)
    all_paths = tuple(item.path for item in planned) + tests
    for path in all_paths:
        validate_scope(path)
        if PurePosixPath(path.replace("\\", "/")).as_posix() != path:
            raise ValueError("scaffold paths must use canonical POSIX spelling")
    if len(all_paths) != len(set(all_paths)):
        raise ValueError("source and test scaffold scopes overlap")
    for path in all_paths:
        if any(PurePosixPath(other) in PurePosixPath(path).parents for other in all_paths if other != path):
            raise ValueError("scaffold file conflicts with another scope's parent directory")
    return _FilePlan(planned, production, tests)


def _checked_path(root: Path, path: str) -> Path:
    resolved = resolve_relative_path(root, path, "approved scaffold path")
    cursor = root
    for part in PurePosixPath(path.replace("\\", "/")).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("scaffold path cannot traverse symlinks")
        if cursor != resolved and cursor.exists() and not cursor.is_dir():
            raise ValueError("scaffold parent is not a directory")
    return resolved


def _validate_files(context: _WorkspaceContext, plan: _FilePlan) -> None:
    root = context.paths.repository_root
    controlled = {item.path for item in context.request.profile.files}
    for item in plan.files:
        target = _checked_path(root, item.path)
        if target.exists() and not target.is_file():
            raise ValueError("approved scaffold file conflicts with an existing directory")
        if target.exists() and item.path in controlled and target.read_text() != item.content:
            raise ValueError("approved scaffold conflicts with existing file: " + item.path)
    for path in plan.test_paths:
        target = _checked_path(root, path)
        if target.exists() and not target.is_file():
            raise ValueError("approved test file conflicts with an existing directory")


def _require_existing_files(context: _WorkspaceContext, plan: _FilePlan) -> None:
    _validate_files(context, plan)
    if any(not _checked_path(context.paths.repository_root, item.path).is_file() for item in plan.files):
        raise ValueError("prepared environment lost an approved scaffold or production file")


def _write_files(context: _WorkspaceContext, plan: _FilePlan) -> None:
    root = context.paths.repository_root
    for item in plan.files:
        target = _checked_path(root, item.path)
        if target.exists():
            if item.path == ".gitignore" and target.read_text() == SEED_GITIGNORE:
                target.write_text(item.content, encoding="utf-8")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as handle:
            handle.write(item.content)
    for path in plan.test_paths:
        _checked_path(root, path).parent.mkdir(parents=True, exist_ok=True)


def _smoke_commands(context: _WorkspaceContext, runner: SetupCommandRunner) -> tuple[CommandResult, ...]:
    results = []
    root = context.paths.repository_root
    for argv in context.request.profile.smoke_commands:
        result = runner.run(SetupCommand(argv, root))
        results.append(result)
        if result.returncode != 0:
            raise WorkspacePreparationError("approved profile smoke command failed", tuple(results))
    if context.request.decision.profile.name == ProfileKind.PYTHON:
        with tempfile.TemporaryDirectory(prefix=SMOKE_DIRECTORY_PREFIX, dir=context.paths.project_root) as name:
            smoke_root = Path(name)
            smoke_test = smoke_root / SMOKE_TEST_NAME
            smoke_test.write_text(SMOKE_TEST_SOURCE, encoding="utf-8")
            argv = (context.runtime.environment_path, "-I", "-B", "-m", "pytest", "-q",
                    "-p", "no:cacheprovider", "--override-ini=addopts=", "--rootdir", name,
                    "--confcutdir", name, str(smoke_test))
            result = runner.run(SetupCommand(argv, smoke_root))
            results.append(result)
            if result.returncode != 0:
                raise WorkspacePreparationError("managed Python pytest smoke failed", tuple(results))
    return tuple(results)
