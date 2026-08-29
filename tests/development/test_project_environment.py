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


def test_project_persists_reloads_and_reuses_runtime(tmp_path):
    first = service(tmp_path).create_or_load_python_project("proof-one")
    second = service(tmp_path).create_or_load_python_project("proof-one")

    assert first == second
    assert first.status == "ready"
    assert first.runtime.kind == "python"
    assert first.runtime.lifetime == "shared"
    assert first.workspace_lifetime == "disposable"
    assert (tmp_path / "projects" / "proof-one" / "project.json").exists()
    assert (tmp_path / "projects" / "proof-one" / "repository" / ".git").exists()


def test_accepted_executor_revision_is_persisted(tmp_path):
    project = service(tmp_path).create_or_load_python_project("accepted-revision")
    root = Path(project.repository_root)
    (root / "marker.txt").write_text("accepted\\n", encoding="utf-8")

    subprocess.run(["git", "add", "marker.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "-qm", "accepted revision"],
        cwd=root,
        check=True,
    )
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    updated = service(tmp_path).record_trusted_revision(project.project_id, revision)

    assert updated.trusted_base_sha == revision
    assert service(tmp_path).create_or_load_python_project(project.project_id).trusted_base_sha == revision


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
        id="smoke", project_id=project.project_id, parent_ticket_id="environment",
        objective="Create one harmless marker file.", allowed_paths=["marker.txt"],
        acceptance=AcceptanceContract(commands=[["true"]], required_artifacts=[]), status=WorkUnitStatus.READY,
    )

    request = to_rack_ai_request("environment-proof", project.binding(), unit)

    assert request["repository"] == {"id": project.project_id, "base_ref": "main", "base_sha": project.trusted_base_sha, "root": project.repository_root}
    assert find_forbidden_resource_selection_keys(request) == []
    assert "python" not in json.dumps(request).lower()
