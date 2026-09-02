import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.development.project_environment import ProjectEnvironmentService
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import find_forbidden_resource_selection_keys, to_rack_ai_request


def service(tmp_path):
    return ProjectEnvironmentService(tmp_path / "projects", python_executable=sys.executable)


def commit_file(root, path, content, message):
    target = root / path
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", path], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", message],
        cwd=root,
        check=True,
    )
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def commit_on_branch(root, branch, path, content, message):
    subprocess.run(["git", "switch", "-c", branch], cwd=root, check=True)
    revision = commit_file(root, path, content, message)
    subprocess.run(["git", "switch", "main"], cwd=root, check=True)
    return revision


def test_project_persists_reloads_and_reuses_runtime(tmp_path):
    first = service(tmp_path).create_or_load_python_project("proof-one")
    second = service(tmp_path).create_or_load_python_project("proof-one")

    assert first == second
    assert first.status == "ready"
    assert first.runtime.kind == "python"
    assert first.runtime.lifetime == "shared"
    assert first.runtime.resource_paths() == [str(Path(sys.executable).parent.parent)]
    assert first.workspace_lifetime == "disposable"
    assert (tmp_path / "projects" / "proof-one" / "project.json").exists()
    assert (tmp_path / "projects" / "proof-one" / "repository" / ".git").exists()


def test_legacy_project_state_without_environment_resources_remains_readable(tmp_path):
    environment = service(tmp_path)
    created = environment.create_or_load_python_project("legacy-runtime")
    state_path = tmp_path / "projects" / "legacy-runtime" / "project.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["runtime"].pop("environment_resources", None)
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded = environment.create_or_load_python_project(created.project_id)

    assert reloaded.project_id == created.project_id
    assert reloaded.runtime.resource_paths() == []
    assert reloaded.binding().environment_resources == []


def test_accepted_executor_revision_is_persisted(tmp_path):
    project = service(tmp_path).create_or_load_python_project("accepted-revision")
    root = Path(project.repository_root)
    revision = commit_on_branch(root, "rack-red", "marker.txt", "accepted\n", "accepted revision")

    updated = service(tmp_path).record_trusted_revision(project.project_id, revision)

    assert updated.trusted_base_sha == revision
    assert subprocess.run(["git", "rev-parse", "main"], cwd=root, check=True, capture_output=True, text=True).stdout.strip() == revision
    reloaded = service(tmp_path).create_or_load_python_project(project.project_id)
    assert reloaded.trusted_base_sha == revision
    assert reloaded.binding().base_sha == revision


def test_trusted_revision_rejects_non_descendant_commit(tmp_path):
    environment = service(tmp_path)
    project = environment.create_or_load_python_project("non-descendant")
    root = Path(project.repository_root)
    accepted = commit_on_branch(root, "rack-accepted", "accepted.txt", "accepted\n", "accepted revision")
    environment.record_trusted_revision(project.project_id, accepted)

    subprocess.run(["git", "switch", "-c", "unrelated", project.trusted_base_sha], cwd=root, check=True)
    unrelated = commit_file(root, "unrelated.txt", "unrelated\n", "unrelated revision")
    subprocess.run(["git", "switch", "main"], cwd=root, check=True)

    with pytest.raises(ValueError, match="fast-forward"):
        environment.record_trusted_revision(project.project_id, unrelated)
    assert environment.repo.load(project.project_id).trusted_base_sha == accepted
    assert subprocess.run(["git", "rev-parse", "main"], cwd=root, check=True, capture_output=True, text=True).stdout.strip() == accepted


def test_trusted_revision_rejects_unknown_or_retired_project(tmp_path):
    environment = service(tmp_path)
    project = environment.create_or_load_python_project("promotion-state")

    with pytest.raises(ValueError, match="unavailable"):
        environment.record_trusted_revision(project.project_id, "a" * 40)

    environment.retire(project.project_id)
    with pytest.raises(ValueError, match="ready"):
        environment.record_trusted_revision(project.project_id, project.trusted_base_sha)


def test_metadata_is_unchanged_when_canonical_promotion_fails(tmp_path, monkeypatch):
    environment = service(tmp_path)
    project = environment.create_or_load_python_project("promotion-failure")
    root = Path(project.repository_root)
    candidate = commit_on_branch(root, "rack-candidate", "candidate.txt", "candidate\n", "candidate revision")
    original_git = environment._git

    def fail_promotion(git_root, *args):
        if args[0] == "update-ref" and args[1] == "refs/heads/main":
            raise subprocess.CalledProcessError(1, ["git", *args])
        return original_git(git_root, *args)

    monkeypatch.setattr(environment, "_git", fail_promotion)

    with pytest.raises(subprocess.CalledProcessError):
        environment.record_trusted_revision(project.project_id, candidate)
    assert environment.repo.load(project.project_id).trusted_base_sha == project.trusted_base_sha
    assert subprocess.run(["git", "rev-parse", "main"], cwd=root, check=True, capture_output=True, text=True).stdout.strip() == project.trusted_base_sha


def test_metadata_persistence_failure_rolls_back_canonical_promotion(tmp_path, monkeypatch):
    environment = service(tmp_path)
    project = environment.create_or_load_python_project("metadata-failure")
    root = Path(project.repository_root)
    candidate = commit_on_branch(root, "rack-candidate", "candidate.txt", "candidate\n", "candidate revision")

    def fail_save(_project):
        raise OSError("disk unavailable")

    monkeypatch.setattr(environment.repo, "save", fail_save)

    with pytest.raises(OSError, match="disk unavailable"):
        environment.record_trusted_revision(project.project_id, candidate)
    assert subprocess.run(["git", "rev-parse", "main"], cwd=root, check=True, capture_output=True, text=True).stdout.strip() == project.trusted_base_sha


def test_invalid_or_missing_state_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="unknown"):
        service(tmp_path).retire("missing")
    path = tmp_path / "projects" / "broken"
    path.mkdir(parents=True)
    (path / "project.json").write_text(json.dumps({"project_id": "broken"}), encoding="utf-8")
    with pytest.raises(KeyError):
        service(tmp_path).create_or_load_python_project("broken")


def test_retirement_only_removes_athba_owned_workspace(tmp_path):
    project = service(tmp_path).create_or_load_python_project("retire-me")
    retired = service(tmp_path).retire(project.project_id, remove_workspace=True)

    assert retired.status == "retired"
    assert not (tmp_path / "projects" / "retire-me" / "repository").exists()
    assert Path(project.runtime.environment_path).is_file()
    with pytest.raises(ValueError, match="retired"):
        service(tmp_path).create_or_load_python_project(project.project_id)


def test_generic_execution_request_has_no_runtime_or_framework_fields(tmp_path):
    project = service(tmp_path).create_or_load_python_project("generic-request")
    unit = DevelopmentWorkUnit(
        id="smoke",
        project_id=project.project_id,
        parent_ticket_id="environment",
        objective="Create one harmless marker file.",
        allowed_paths=["marker.txt"],
        acceptance=AcceptanceContract(commands=[["true"]], required_artifacts=[]),
        status=WorkUnitStatus.READY,
    )

    request = to_rack_ai_request("environment-proof", project.binding(), unit)

    assert request["repository"] == {"id": project.project_id, "base_ref": "main", "base_sha": project.trusted_base_sha, "root": project.repository_root}
    assert request["environment_resources"] == [str(Path(sys.executable).parent.parent)]
    assert find_forbidden_resource_selection_keys(request) == []
    assert "python" not in json.dumps(request).lower()
