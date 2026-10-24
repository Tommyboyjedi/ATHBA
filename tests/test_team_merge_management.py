"""Controlled completion authorities exercise real Git/regression management, not live BDE builds."""
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
import subprocess
import sys

import pytest

from core.atomic_json_file import read_json_file, write_json_atomically
from core.delivery_management.domain import DeliveryPhase, ManagementRequest, MergeKind, MergeRecord, MergeStatus, TeamDelivery
from core.delivery_management.evidence import AcceptedContribution, AcceptedNode, AcceptedSourceReader
from core.delivery_management.git_workspaces import BranchWorkspace, GitCommand, GitWorkspaces, git
from core.delivery_management.merge_service import MergeDependencies, MergeManagement
from core.delivery_management.store import ManagementStore, RecordIdentity
from core.delivery_management.validation import IntegrationValidationDependencies, IntegrationValidator
from core.development.consolidation_language import ConsolidationLanguage
from core.development.deterministic_regression import SubprocessProjectRuntimeExecutor
from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService, ProjectRuntime
from core.development.python_pytest_adapter import PythonPytestAdapter
from core.development.python_test_material import PythonTestMaterial
from core.project_setup.architecture import FullBehavior


def commit(root: Path, message: str = "controlled branch checkpoint") -> str:
    git(GitCommand(root, ("add", "-A")))
    git(GitCommand(root, ("-c", "user.name=Controlled Proof", "-c", "user.email=proof@example.invalid",
                          "commit", "-qm", message)))
    return git(GitCommand(root, ("rev-parse", "HEAD")))


@dataclass(frozen=True)
class ControlledObservation:
    name: str
    expected: int = 2
    comment: str = "initial controlled fixture"


@dataclass
class ManagedFixture:
    root: Path
    repository: Path
    environment: ProjectEnvironmentService
    store: ManagementStore
    service: MergeManagement
    base_revision: str

    def delivery(self, example: ControlledObservation) -> TeamDelivery:
        branch = self.root / "branches" / example.name
        branch_ref = "refs/heads/delivery/" + example.name
        GitWorkspaces().prepare(BranchWorkspace(self.repository, branch, branch_ref,
            self.base_revision, self.root / "branches", "refs/heads/release"))
        (branch / "common.py").write_text(
            f'"""{example.comment}"""\ndef value():\n    return {example.expected}\n')
        (branch / "tests").mkdir()
        test_path = f"tests/test_{example.name}.py"
        test_name = test_path + "::test_observation"
        (branch / test_path).write_text(
            f"from common import value\n\ndef test_observation():\n    assert value() == {example.expected}\n")
        revision = commit(branch)
        source = AcceptedSourceReader(branch, PythonTestMaterial()).source((revision, test_name))
        requirement = f"Controlled fixture {example.name}: the observed value is {example.expected}."
        behavior = FullBehavior(example.name, requirement, sha256(requirement.encode()).hexdigest(),
                                ("common.py",), (test_path,))
        contribution = AcceptedContribution("application", example.name, example.name,
            behavior.source_sha256, "controlled-architecture", revision, requirement,
            (AcceptedNode(test_name, test_path, sha256(source.encode()).hexdigest(), revision,
                ("REQ001",), ("SRC001",), "common.py", example.name),),
            ("controlled-completion-fixture-only:" + example.name,))
        authority = self.store.directory("application") / "authority" / f"{example.name}.json"
        write_json_atomically(authority, contribution.to_dict())
        record = TeamDelivery(example.name, "application", behavior, "controlled-architecture",
            1, "controlled-specification", 1, branch_ref, str(branch), str(self.root / "state" / example.name),
            self.base_revision, self.base_revision, revision, phase=DeliveryPhase.COMPLETE,
            completion_revision=revision, authority_file=str(authority),
            authority_sha256=sha256(authority.read_bytes()).hexdigest(), naming="NO", refactoring="NO")
        self.store.save_delivery(record)
        return record

    def prepare(self, name: str):
        return self.service.prepare(ManagementRequest("application", name, "controlled-manager"),
                                    MergeKind.INTEGRATION)

    def publish(self, operation):
        identity = RecordIdentity("application", operation.id)
        approval = self.service.approve(identity, "controlled-manager")
        return self.service.promote(identity, approval)


def managed(root: Path) -> ManagedFixture:
    environment = ProjectEnvironmentService(root / "projects")
    repository = root / "projects" / "application" / "repository"
    repository.mkdir(parents=True)
    git(GitCommand(repository, ("init", "-q", "-b", "release")))
    (repository / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    (repository / "common.py").write_text('"""initial controlled fixture"""\ndef value():\n    return 2\n')
    base = commit(repository, "controlled application seed")
    runtime = ProjectRuntime("python", sys.version.split()[0], sys.executable,
        [sys.executable, "-m", "pytest", "-q", "-p", "no:django", "-p", "no:asyncio"])
    environment.repo.save(DevelopmentProject("application", str(repository), "release",
        base, runtime, ["__pycache__", ".pytest_cache"], "ready"))
    store = ManagementStore(root / "projects")
    store.save_catalog(("application", {"revision": base, "authority_files": [],
        "authority_hashes": {}, "integrated_deliveries": []}))
    material = PythonTestMaterial()
    validator = IntegrationValidator(IntegrationValidationDependencies(material,
        ConsolidationLanguage(PythonPytestAdapter(), material), SubprocessProjectRuntimeExecutor()))
    return ManagedFixture(root, repository, environment, store,
        MergeManagement(MergeDependencies(store, environment, validator)), base)


def test_two_completed_branches_stale_integration_then_sync_preserves_both_test_sets(tmp_path):
    fixture = managed(tmp_path)
    fixture.delivery(ControlledObservation("first"))
    second = fixture.delivery(ControlledObservation("second"))
    first_operation, second_operation = fixture.prepare("first"), fixture.prepare("second")
    assert first_operation.status == second_operation.status == MergeStatus.VALIDATED
    assert fixture.environment.repo.load("application").trusted_base_sha == fixture.base_revision
    second_identity = RecordIdentity("application", second_operation.id)
    approval = fixture.service.approve(second_identity, "controlled-manager")
    assert fixture.publish(first_operation).status == MergeStatus.PUBLISHED
    assert fixture.service.promote(second_identity, approval).status == MergeStatus.STALE
    sync = fixture.service.request_sync(ManagementRequest("application", "second", "controlled-manager"))
    assert sync.status == MergeStatus.PUBLISHED
    current = fixture.store.delivery(RecordIdentity("application", "second"))
    assert current.completion_revision == second.completion_revision
    assert current.scope_base_revision == current.trusted_revision == sync.candidate_revision
    assert current.synchronized_main == first_operation.candidate_revision
    fresh = fixture.prepare("second")
    assert fresh.status == MergeStatus.VALIDATED
    assert fixture.publish(fresh).status == MergeStatus.PUBLISHED
    catalog = fixture.store.catalog("application")
    assert set(catalog["integrated_deliveries"]) == {"first", "second"}
    assert len(catalog["authority_files"]) == 2
    assert (fixture.repository / "tests/test_first.py").is_file()
    assert (fixture.repository / "tests/test_second.py").is_file()
    git(GitCommand(fixture.repository, ("merge-base", "--is-ancestor",
                                       first_operation.candidate_revision, fresh.candidate_revision)))


def test_clean_merge_failing_combined_regression_leaves_main_and_completion_intact(tmp_path):
    fixture = managed(tmp_path)
    fixture.delivery(ControlledObservation("first"))
    second = fixture.delivery(ControlledObservation("second", expected=3))
    first_operation = fixture.prepare("first")
    assert fixture.publish(first_operation).status == MergeStatus.PUBLISHED
    before = fixture.environment.repo.load("application").trusted_base_sha
    failed = fixture.prepare("second")
    assert failed.status == MergeStatus.FAILED
    assert failed.candidate_revision and not failed.conflicts
    assert fixture.environment.repo.load("application").trusted_base_sha == before
    assert git(GitCommand(fixture.repository, ("rev-parse", "HEAD"))) == before
    assert fixture.store.delivery(RecordIdentity("application", "second")).phase == DeliveryPhase.COMPLETE
    assert second.completion_revision == fixture.store.delivery(RecordIdentity("application", "second")).completion_revision
    report = next(read_json_file(Path(ref)) for ref in failed.evidence_refs
                  if Path(ref).is_absolute() and "commands" in read_json_file(Path(ref)))
    assert any(item["status"] == "failed" for item in report["commands"])


def test_conflict_and_explicit_resolution_use_the_same_combined_acceptance_pipeline(tmp_path):
    fixture = managed(tmp_path)
    fixture.delivery(ControlledObservation("first", comment="first comment"))
    second = fixture.delivery(ControlledObservation("second", comment="second comment"))
    first_operation = fixture.prepare("first")
    fixture.publish(first_operation)
    main = fixture.environment.repo.load("application").trusted_base_sha
    conflict = fixture.prepare("second")
    assert conflict.status == MergeStatus.CONFLICT and conflict.conflicts == ("common.py",)
    assert git(GitCommand(fixture.repository, ("rev-parse", "HEAD"))) == main
    assert not (fixture.store.directory("application") / "trials" / conflict.id).exists()
    supplied = tmp_path / "explicitly-supplied-resolution"
    git(GitCommand(fixture.repository, ("worktree", "add", "--detach", str(supplied), main)))
    result = subprocess.run(("git", "-c", "user.name=Controlled Proof", "-c",
        "user.email=proof@example.invalid", "merge", "--no-commit", "--no-ff", second.completion_revision),
        cwd=supplied, capture_output=True, text=True)
    assert result.returncode == 1
    (supplied / "common.py").write_text('"""first and second comments"""\ndef value():\n    return 2\n')
    resolution = commit(supplied, "explicit controlled conflict resolution")
    (supplied / "unrelated.py").write_text("UNREQUESTED = True\n")
    unrelated = commit(supplied, "unattributed addition must not enter through resolution")
    rejected = fixture.service.validate_resolution(RecordIdentity("application", conflict.id), unrelated)
    assert rejected.status == MergeStatus.FAILED
    assert "unattributed path" in rejected.reason
    assert git(GitCommand(fixture.repository, ("rev-parse", "HEAD"))) == main
    assert not (fixture.repository / "unrelated.py").exists()
    resolved = fixture.service.validate_resolution(RecordIdentity("application", conflict.id), resolution)
    assert resolved.status == MergeStatus.VALIDATED
    assert resolved.candidate_revision == resolution
    assert fixture.publish(resolved).status == MergeStatus.PUBLISHED
    assert (fixture.repository / "tests/test_first.py").is_file()
    assert (fixture.repository / "tests/test_second.py").is_file()
    history = [read_json_file(Path(ref)) for ref in resolved.evidence_refs
               if Path(ref).is_absolute() and "-prior-" in ref]
    assert any(item["status"] == MergeStatus.CONFLICT for item in history)


def test_interrupted_publication_recovers_exact_candidate_without_overwriting_newer_main(tmp_path, monkeypatch):
    fixture = managed(tmp_path)
    fixture.delivery(ControlledObservation("first"))
    operation = fixture.prepare("first")
    identity = RecordIdentity("application", operation.id)
    approval = fixture.service.approve(identity, "controlled-manager")
    original = fixture.environment.repo.save
    def fail_after_git(project):
        raise OSError("controlled metadata interruption")
    with monkeypatch.context() as context:
        context.setattr(fixture.environment.repo, "save", fail_after_git)
        with pytest.raises(OSError, match="interruption"):
            fixture.service.promote(identity, approval)
    assert fixture.store.merge(identity).publication_intent
    assert git(GitCommand(fixture.repository, ("rev-parse", "HEAD"))) == operation.candidate_revision
    assert fixture.environment.repo.load("application").trusted_base_sha == fixture.base_revision
    recovered = fixture.service.recover(identity)
    assert recovered.status == MergeStatus.PUBLISHED
    assert fixture.environment.repo.load("application").trusted_base_sha == operation.candidate_revision
    other = managed(tmp_path / "other")
    other.delivery(ControlledObservation("first"))
    pending = other.prepare("first")
    pending_identity = RecordIdentity("application", pending.id)
    pending_approval = other.service.approve(pending_identity, "controlled-manager")
    with monkeypatch.context() as context:
        context.setattr(other.environment.repo, "save", fail_after_git)
        with pytest.raises(OSError):
            other.service.promote(pending_identity, pending_approval)
    (other.repository / "operator-note.txt").write_text("newer accepted external authority\n")
    newer = commit(other.repository, "controlled newer main")
    project = other.environment.repo.load("application")
    other.environment.repo.save(replace(project, trusted_base_sha=newer))
    with pytest.raises(ValueError, match="newer"):
        other.service.recover(pending_identity)
    assert git(GitCommand(other.repository, ("rev-parse", "HEAD"))) == newer
    assert other.environment.repo.load("application").trusted_base_sha == newer


def test_long_merge_validation_does_not_hold_the_application_integration_lock(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    fixture = managed(tmp_path)
    fixture.delivery(ControlledObservation("first"))
    original = fixture.service.dependencies.validator
    entered, release = threading.Event(), threading.Event()
    class PausingValidator:
        def validate(self, request):
            entered.set()
            assert release.wait(timeout=30)
            return original.validate(request)
    fixture.service = MergeManagement(MergeDependencies(fixture.store, fixture.environment, PausingValidator()))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(fixture.prepare, "first")
        assert entered.wait(timeout=30)
        try:
            with fixture.store.locked(("application", "integration")):
                assert fixture.environment.repo.load("application").trusted_base_sha == fixture.base_revision
            second = fixture.delivery(ControlledObservation("second"))
            assert second.phase == DeliveryPhase.COMPLETE
            request = ManagementRequest("application", "second", "controlled-manager")
            with fixture.store.locked(("application", "integration")):
                git(GitCommand(fixture.repository, ("-c", "user.name=Controlled Proof", "-c",
                    "user.email=proof@example.invalid", "commit", "--allow-empty", "-qm", "newer accepted main")))
                newer = git(GitCommand(fixture.repository, ("rev-parse", "HEAD")))
                parent = fixture.environment.repo.load("application")
                fixture.environment.repo.save(replace(parent, trusted_base_sha=newer))
                catalog = fixture.store.catalog("application")
                fixture.store.save_catalog(("application", {**catalog, "revision": newer}))
                deferred = fixture.service.request_sync(request)
                assert deferred.status == MergeStatus.DEFERRED
                current = fixture.store.delivery(RecordIdentity("application", "second"))
                assert current.pending_sync and current.pending_sync_revision == newer
                from core.delivery_management.merge_service import clear_pending_sync
                old = MergeRecord("older-sync", "application", "second", MergeKind.SYNCHRONIZATION,
                    fixture.base_revision, second.trusted_revision)
                clear_pending_sync(fixture.service.dependencies, old)
                current = fixture.store.delivery(RecordIdentity("application", "second"))
                assert current.pending_sync and current.pending_sync_revision == newer
            release.set()
            synchronized = fixture.service.request_sync(request)
            assert synchronized.status == MergeStatus.PUBLISHED, synchronized.reason
            current = fixture.store.delivery(RecordIdentity("application", "second"))
            assert not current.pending_sync and current.pending_sync_revision is None
            assert git(GitCommand(fixture.repository, ("rev-parse", "HEAD"))) == newer
        finally:
            release.set()
        assert pending.result(timeout=30).status == MergeStatus.VALIDATED
