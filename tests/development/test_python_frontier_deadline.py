"""Existing structured frontier execution remains bounded and test-immutable."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

import core.development.python_pytest_adapter as adapter_module
from core.development.deterministic_regression import (
    DeterministicRegressionRequest, DeterministicRegressionService, REGRESSION_CLEAR,
    SubprocessProjectRuntimeExecutor,
)
from core.development.microcycle_domain import (
    BoundaryClassificationRequest, FragmentationRequest, FrontierExecutionRequest,
    FrontierMaterialisationRequest, ScenarioFrontier, ScenarioParseRequest, TestScenarioDraft,
)
from core.development.python_pytest_adapter import PythonPytestAdapter, PytestStructuredExecutor

TEST_PATH = "tests/test_current.py"
NODE = TEST_PATH + "::test_current"
SOURCE = "from app import operation\n\ndef test_current():\n    assert operation() == 7\n"


def prepared():
    adapter = PythonPytestAdapter()
    draft = TestScenarioDraft("one-scenario", "one-behavior", "python", SOURCE, NODE, TEST_PATH)
    model = adapter.parse_scenario(ScenarioParseRequest(draft))
    fragments = adapter.fragment_scenario(FragmentationRequest(model))
    index = len(fragments) - 1
    frontier = ScenarioFrontier(model.scenario_id, index, fragments[index].fragment_id,
        tuple(item.fragment_id for item in fragments))
    artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(model, fragments, frontier, "accepted-red"))
    return adapter, artifact, fragments[-1]


def request(tmp_path, **kwargs):
    _adapter, artifact, _fragment = prepared()
    return FrontierExecutionRequest(artifact, str(tmp_path), TEST_PATH, "app.py", **kwargs)


def passed_facts():
    return {
        "collection_succeeded": True, "requested_node_found": True, "requested_node_executed": True,
        "outcome": "passed", "setup_outcome": "passed", "call_outcome": "passed", "teardown_outcome": "passed",
        "was_xfail": False, "was_xpass": False, "missing_production_member": False,
        "exception_type": None, "failure_message": None, "traceback_location": None, "source_line": None,
        "stdout": "", "stderr": "", "evidence_refs": [NODE],
    }


def capture_run(monkeypatch):
    observed = []

    def run(command, **kwargs):
        observed.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps(passed_facts()) + "\n", "")

    monkeypatch.setattr(adapter_module.subprocess, "run", run)
    return observed


def test_ordinary_execution_keeps_existing_thirty_second_limit(tmp_path, monkeypatch):
    observed = capture_run(monkeypatch)
    result = PytestStructuredExecutor().execute(request(tmp_path))

    assert result.kind == "green"
    assert observed[0][1]["timeout"] == 30.0


def test_deadline_uses_smaller_remaining_time_without_increasing_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter_module.time, "monotonic", lambda: 100.0)
    observed = capture_run(monkeypatch)
    result = PytestStructuredExecutor().execute(request(tmp_path, deadline=102.5))

    assert result.kind == "green"
    assert observed[0][1]["timeout"] == 2.5

    PytestStructuredExecutor().execute(request(tmp_path, deadline=1000.0))
    assert observed[1][1]["timeout"] == 30.0


def test_already_expired_deadline_does_not_launch_or_materialise_test(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter_module.time, "monotonic", lambda: 100.0)
    observed = capture_run(monkeypatch)

    result = PytestStructuredExecutor().execute(request(tmp_path, deadline=100.0))

    assert result.kind == "infrastructure"
    assert observed == []
    assert not (tmp_path / TEST_PATH).exists()


def test_deadline_is_rechecked_after_setup_before_subprocess(tmp_path, monkeypatch):
    readings = iter((100.0, 103.0))
    monkeypatch.setattr(adapter_module.time, "monotonic", lambda: next(readings))
    observed = capture_run(monkeypatch)

    result = PytestStructuredExecutor().execute(request(tmp_path, deadline=102.0))

    assert result.kind == "infrastructure"
    assert observed == []


def test_bounded_probe_timeout_is_explicit_infrastructure_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setattr(adapter_module.time, "monotonic", lambda: 100.0)

    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(adapter_module.subprocess, "run", run)
    result = PytestStructuredExecutor().execute(request(tmp_path, deadline=101.0))

    assert result.kind == "infrastructure"
    assert "deadline" in result.message


def test_ordinary_timeout_exception_behavior_remains_unchanged(tmp_path, monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(adapter_module.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        PytestStructuredExecutor().execute(request(tmp_path))


def test_existing_test_mode_preserves_merged_prior_test_bytes(tmp_path, monkeypatch):
    target = tmp_path / TEST_PATH
    target.parent.mkdir()
    source = SOURCE + "\ndef test_prior():\n    assert True\n"
    target.write_text(source)
    observed = capture_run(monkeypatch)

    result = PytestStructuredExecutor().execute(request(tmp_path, materialise_test=False))

    assert result.kind == "green"
    assert target.read_text() == source
    assert "test_prior" not in request(tmp_path).artifact.complete_source
    assert observed[0][0][-2] == NODE


def test_existing_test_mode_fails_closed_without_creating_missing_authority(tmp_path, monkeypatch):
    observed = capture_run(monkeypatch)

    result = PytestStructuredExecutor().execute(request(tmp_path, materialise_test=False))

    assert result.kind == "infrastructure"
    assert "missing" in result.message
    assert observed == []
    assert not (tmp_path / TEST_PATH).exists()


def test_plain_exit_zero_skip_is_not_independent_frontier_green(tmp_path):
    adapter, artifact, fragment = prepared()
    production = (
        "import unittest\nENABLED = True\n\ndef operation():\n"
        "    if 'ENABLED' not in globals():\n"
        "        raise unittest.SkipTest('not ready')\n"
        "    return 7\n"
    )
    path = tmp_path / "app.py"
    path.write_text(production)
    initial = adapter.execute_frontier(FrontierExecutionRequest(
        artifact, str(tmp_path), TEST_PATH, "app.py", deadline=time.monotonic() + 20.0))
    assert initial.kind == "green"
    test_before = (tmp_path / TEST_PATH).read_bytes()

    # A complete production statement deletion; tests and expected values stay fixed.
    path.write_text(production.replace("ENABLED = True\n", ""))
    plain = DeterministicRegressionService(SubprocessProjectRuntimeExecutor()).run(
        DeterministicRegressionRequest(tmp_path, (sys.executable, "-m", "pytest", "-q"), NODE))
    assert plain.status == REGRESSION_CLEAR
    assert all(item.return_code == 0 for item in plain.reports)
    assert any("skipped" in item.evidence_ref for item in plain.reports)

    diagnostic = adapter.execute_frontier(FrontierExecutionRequest(
        artifact, str(tmp_path), TEST_PATH, "app.py",
        deadline=time.monotonic() + 20.0, materialise_test=False))
    assessment = adapter.classify_boundary(BoundaryClassificationRequest(
        diagnostic, artifact, fragment, "green"))

    assert diagnostic.kind != "green"
    assert assessment.outcome != "green"
    assert {item.name: item.value for item in diagnostic.facts}["call_outcome"] == "skipped"
    assert (tmp_path / TEST_PATH).read_bytes() == test_before
