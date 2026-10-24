"""Real disposable-Git recovery of owned setup failures; controlled storage only."""
from dataclasses import dataclass, field
import json
from pathlib import Path

import pytest

from core.development.project_environment_store import ProjectEnvironmentRepo
from core.project_setup.commands import CommandResult
from core.project_setup.records import SetupStatus
from tests.test_approved_project_setup import approved, environment, git


@dataclass
class RunnerProbe:
    original: object
    progress: Path
    init_snapshots: list = field(default_factory=list)
    smoke_calls: int = 0
    fail_smoke: bool = True

    def run(self, request):
        if request.argv[:2] == ("git", "init"):
            snapshot = json.loads(self.progress.read_text()) if self.progress.exists() else None
            self.init_snapshots.append(snapshot)
        if any("test_environment_smoke.py" in argument for argument in request.argv):
            self.smoke_calls += 1
            if self.fail_smoke:
                return CommandResult(request.argv, 1, "controlled setup smoke failed", "")
        return self.original(request)


async def failed_setup(tmp_path, monkeypatch):
    handoff, _, app = environment(tmp_path, approved())
    root = tmp_path / "projects" / handoff.decision.project_id
    runner = app.setup.dependencies.runner
    probe = RunnerProbe(runner.run, root / "setup-progress.json")
    monkeypatch.setattr(runner, "run", probe.run)
    with pytest.raises(Exception, match="smoke"):
        await app.setup.prepare(handoff)
    failed = app.records.load(handoff.decision.project_id)
    assert failed.status == SetupStatus.FAILED and not failed.environment_verified
    assert ProjectEnvironmentRepo(tmp_path / "projects").load(failed.project_id) is None
    assert not (root / "project.json").exists()
    return handoff, app, probe


@pytest.mark.asyncio
async def test_owned_setup_smoke_failure_retries_same_seed_and_becomes_idempotent_ready(tmp_path, monkeypatch):
    handoff, app, probe = await failed_setup(tmp_path, monkeypatch)
    root = tmp_path / "projects" / handoff.decision.project_id
    repository = root / "repository"
    original_failure = app.records.load(handoff.decision.project_id)
    seed = git(repository, "rev-parse", "HEAD")
    assert len(probe.init_snapshots) == 1
    assert probe.init_snapshots[0] is not None, "setup ownership must be durable before Git initialization"
    assert "seed_revision" in probe.init_snapshots[0] and "expected_files" in probe.init_snapshots[0]
    progress = json.loads(probe.progress.read_text())
    assert progress["seed_revision"] == seed
    assert isinstance(progress["expected_files"], dict)
    assert set(path for behavior in handoff.decision.behaviors for path in behavior.production_paths) <= set(progress["expected_files"])
    assert git(repository, "rev-list", "--count", "HEAD") == "1"

    probe.fail_smoke = False  # Restore actual command execution; keep the observation spy.
    ready = await app.setup.prepare(handoff)
    assert ready.status == SetupStatus.READY and ready.environment_verified
    assert Path(ready.repository_root) == repository
    assert ProjectEnvironmentRepo(tmp_path / "projects").load(ready.project_id).trusted_base_sha == ready.scaffold_revision
    assert git(repository, "rev-parse", "HEAD~1") == seed
    assert git(repository, "rev-list", "--count", "HEAD") == "2"
    assert len(probe.init_snapshots) == 1 and probe.smoke_calls == 2
    assert any("test_environment_smoke.py" in " ".join(command.argv)
               and command.returncode == 0 and "1 passed" in command.stdout for command in ready.commands)
    failures = [json.loads(path.read_text()) for path in (root / "setup-failures").glob("*.json")]
    assert any(item["status"] == "failed" and item["project_id"] == original_failure.project_id
               and any(command["stdout"] == "controlled setup smoke failed" for command in item["commands"])
               for item in failures)

    head = git(repository, "rev-parse", "HEAD")
    assert await app.setup.prepare(handoff) == ready
    assert git(repository, "rev-parse", "HEAD") == head
    assert git(repository, "rev-list", "--count", "HEAD") == "2"
    assert len(probe.init_snapshots) == 1 and probe.smoke_calls == 2
    assert not git(repository, "status", "--porcelain")


@pytest.mark.asyncio
async def test_owned_setup_retry_refuses_unexpected_files_and_edits_without_mutation(tmp_path, monkeypatch):
    handoff, app, probe = await failed_setup(tmp_path, monkeypatch)
    root = tmp_path / "projects" / handoff.decision.project_id
    repository = root / "repository"
    production = repository / handoff.decision.behaviors[0].production_paths[0]
    production.write_text("# independent user edit must survive\n")
    unexpected = repository / "operator-note.txt"
    unexpected.write_text("independent staged material must survive\n")
    git(repository, "add", "--", unexpected.name)
    files = {path.relative_to(repository).as_posix(): path.read_bytes()
             for path in repository.rglob("*") if path.is_file() and ".git" not in path.relative_to(repository).parts}
    before_head = git(repository, "rev-parse", "HEAD")
    before_index = git(repository, "write-tree")
    before_staged = git(repository, "diff", "--cached", "--binary")
    before_status = git(repository, "status", "--porcelain", "--untracked-files=all")
    probe.fail_smoke = False
    with pytest.raises(Exception):
        await app.setup.prepare(handoff)
    assert git(repository, "rev-parse", "HEAD") == before_head
    assert git(repository, "write-tree") == before_index
    assert git(repository, "diff", "--cached", "--binary") == before_staged
    assert git(repository, "status", "--porcelain", "--untracked-files=all") == before_status
    assert files == {path.relative_to(repository).as_posix(): path.read_bytes()
                     for path in repository.rglob("*") if path.is_file() and ".git" not in path.relative_to(repository).parts}
    assert probe.smoke_calls == 1 and len(probe.init_snapshots) == 1
    assert ProjectEnvironmentRepo(tmp_path / "projects").load(handoff.decision.project_id) is None
    assert not (root / "project.json").exists()
    assert app.records.load(handoff.decision.project_id).status == SetupStatus.FAILED


@pytest.mark.asyncio
async def test_prejournal_failed_setup_requires_exact_evidence_before_recovering_same_seed(tmp_path, monkeypatch):
    from dataclasses import asdict, replace
    from hashlib import sha256
    import subprocess
    from core.project_setup.recovery import (
        HistoricalSetupEvidence, SetupEvidenceFile,
    )

    handoff, app, probe = await failed_setup(tmp_path, monkeypatch)
    root = tmp_path / "projects" / handoff.decision.project_id
    repository = root / "repository"
    seed = git(repository, "rev-parse", "HEAD")
    files = {path.relative_to(repository).as_posix(): sha256(path.read_bytes()).hexdigest()
             for path in repository.rglob("*") if path.is_file() and ".git" not in path.relative_to(repository).parts}
    assert len(files) == 6
    status = subprocess.run(("git", "status", "--short"), cwd=repository,
        check=True, capture_output=True, text=True).stdout
    retained = root / "historical-evidence"
    retained.mkdir()
    def evidence_file(name, payload):
        path = retained / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return SetupEvidenceFile(path, sha256(path.read_bytes()).hexdigest())
    failed = evidence_file("failed-setup.json", asdict(app.records.load(handoff.decision.project_id)))
    run = evidence_file("failed-run.json", {
        "approved_handoff": asdict(handoff), "state_root": str(tmp_path),
        "project_id": handoff.decision.project_id, "status": "failed",
        "prepare_requested": True, "bde_execution_attempted": False, "model_interactions": 0,
    })
    snapshot = evidence_file("repository-snapshot.json", {
        "repository": str(repository), "head": seed, "status": status, "files_sha256": files,
        "trusted_scaffold_revision": None, "delivery_branches": [], "integration_receipts": [],
    })
    evidence = HistoricalSetupEvidence(failed, run, snapshot)
    probe.progress.unlink()  # Disposable fixture represents a retained failure from before journals existed.
    references = git(repository, "show-ref")
    index = git(repository, "write-tree")
    bad = replace(evidence, failed_run=replace(run, sha256="0" * 64))
    with pytest.raises(ValueError, match="hash"):
        await app.setup.recover(handoff, bad)
    assert not probe.progress.exists()
    assert ProjectEnvironmentRepo(tmp_path / "projects").load(handoff.decision.project_id) is None
    assert git(repository, "show-ref") == references
    assert git(repository, "rev-parse", "HEAD") == seed and git(repository, "write-tree") == index
    assert files == {path.relative_to(repository).as_posix(): sha256(path.read_bytes()).hexdigest()
                     for path in repository.rglob("*") if path.is_file() and ".git" not in path.relative_to(repository).parts}

    probe.fail_smoke = False
    ready = await app.setup.recover(handoff, evidence)
    assert ready.status == SetupStatus.READY and ready.environment_verified
    assert git(repository, "rev-parse", "HEAD~1") == seed
    assert git(repository, "rev-list", "--count", "HEAD") == "2"
    assert len(probe.init_snapshots) == 1 and probe.smoke_calls == 2
    progress = json.loads(probe.progress.read_text())
    assert progress["seed_revision"] == seed
    assert progress["provenance"] == [[str(reference.path), reference.sha256]
                                     for reference in (failed, run, snapshot)]
