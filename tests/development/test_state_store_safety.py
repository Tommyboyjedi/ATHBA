import json

import pytest

from core.atomic_json_file import write_json_atomically
from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.datastore.repos.work_unit_state_repo import WorkUnitStateRepo
from core.development.project_environment_store import ProjectEnvironmentRepo


@pytest.mark.parametrize("project_id", ["", ".", "..", " ../escape", "../escape", "nested/path", r"nested\\path", "/tmp/outside"])
def test_state_repositories_reject_unsafe_project_ids(tmp_path, project_id):
    repos = [
        ProjectEnvironmentRepo(tmp_path),
        TddStateRepo(tmp_path),
        WorkUnitStateRepo(tmp_path),
    ]

    for repo in repos:
        with pytest.raises(ValueError):
            repo._path_for(project_id)


def test_atomic_json_write_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    target.write_text(json.dumps({"old": True}), encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("disk full")

    monkeypatch.setattr("core.atomic_json_file.os.replace", fail_replace)

    with pytest.raises(OSError, match="disk full"):
        write_json_atomically(target, {"new": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"old": True}
    assert list(tmp_path.glob(".state.json.*.tmp")) == []
