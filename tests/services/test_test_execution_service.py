from pathlib import Path

import pytest

from core.services.service_requests import TestRunRequest
from core.services.test_execution_service import TestExecutionService


def test_get_test_files_discovers_nested_tests_and_skips_dot_git(tmp_path):
    repo = tmp_path / "repo-1"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "test_hidden.py").write_text("def test_hidden():\n    assert True\n", encoding="utf-8")
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_one.py").write_text("def test_one():\n    assert True\n", encoding="utf-8")
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "feature_test.py").write_text("def test_feature():\n    assert True\n", encoding="utf-8")

    service = TestExecutionService(repos_base_path=tmp_path)

    assert service.get_test_files("repo-1") == ["pkg/feature_test.py", "tests/test_one.py"]


@pytest.mark.asyncio
async def test_run_tests_rejects_unsafe_project_id(tmp_path):
    service = TestExecutionService(repos_base_path=tmp_path)

    result = await service.run_tests(TestRunRequest(project_id="../escape", test_files=None))

    assert result["status"] == "error"
    assert "project id" in result["output"]


@pytest.mark.asyncio
async def test_run_tests_rejects_test_file_traversal(tmp_path):
    repo = tmp_path / "repo-1"
    repo.mkdir()
    service = TestExecutionService(repos_base_path=tmp_path)

    result = await service.run_tests(TestRunRequest(project_id="repo-1", test_files=["../escape.py"]))

    assert result["status"] == "error"
    assert "test file path" in result["output"]


@pytest.mark.asyncio
async def test_run_tests_rejects_absolute_test_file_path(tmp_path):
    repo = tmp_path / "repo-1"
    repo.mkdir()
    service = TestExecutionService(repos_base_path=tmp_path)

    result = await service.run_tests(TestRunRequest(project_id="repo-1", test_files=[str(Path("/tmp/outside.py"))]))

    assert result["status"] == "error"
    assert "test file path" in result["output"]
