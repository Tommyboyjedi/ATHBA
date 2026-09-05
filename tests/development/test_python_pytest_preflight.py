"""Readiness gates use only deterministic probes and fake model boundaries."""
import json
from pathlib import Path
import subprocess
from unittest.mock import AsyncMock, Mock

import pytest

from core.development.microcycle_domain import BoundaryDiagnostic
from core.development.python_pytest_preflight import PythonProbePreflightError, PythonPytestPreflight
from core.development.strict_tdd_live_run_composition import (
    StrictTddLiveRunCompositionFactory, StrictTddLiveRunCompositionRequest, StrictTddLiveRunConfiguration,
)
from scripts.run_pr23_strict_tdd_feature import main


def configuration(tmp_path):
    return StrictTddLiveRunConfiguration(
        tmp_path / "state", tmp_path / "evidence", tmp_path / "repository", "preflight-test",
        athba_revision="athba-test", rack_ai_revision="rack-test",
    )


def test_real_preflight_needs_no_production_capability_or_django_secret(tmp_path, monkeypatch):
    for name in ("DJANGO_SECRET_KEY", "DJANGO_SETTINGS_MODULE"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "pytest.ini").write_text("[pytest]\nDJANGO_SETTINGS_MODULE = nonexistent_harness_settings\n")
    (tmp_path / "manage.py").write_text("# harness application\n")
    result = PythonPytestPreflight().check(tmp_path / "probes")
    assert result.kind == "green", result.to_dict()
    facts = {item.name: item.value for item in result.facts}
    assert facts["requested_node_executed"] == "True"
    assert facts["call_outcome"] == "passed"
    assert list((tmp_path / "probes").iterdir()) == []
    assert not (tmp_path / "repository").exists()


@pytest.mark.parametrize("failure", [
    subprocess.CompletedProcess([], 1, "", "pytest failed to initialize"),
    subprocess.CompletedProcess([], 0, " \n\t", ""),
    subprocess.CompletedProcess([], 0, "not JSON", ""),
    subprocess.CompletedProcess([], 0, '{"outcome": "passed"}', ""),
    FileNotFoundError("Python runtime unavailable"),
    subprocess.TimeoutExpired(["python", "-m", "probe"], 30, output=b"partial", stderr=b"startup stalled"),
])
def test_failed_preflight_blocks_all_model_backed_composition(tmp_path, monkeypatch, failure):
    child = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
    monkeypatch.setattr("core.development.python_pytest_adapter.subprocess.run", child)
    compose = Mock(side_effect=AssertionError("Planner/Tester/Intent/Developer must not be composed"))
    monkeypatch.setattr("core.development.strict_tdd_live_run_composition.StrictTddFeatureCompositionFactory.build", compose)
    live_reasoning = Mock(side_effect=AssertionError("No model readiness or generation"))
    monkeypatch.setattr(StrictTddLiveRunCompositionFactory, "_live_reasoning", live_reasoning)
    reasoning = Mock(reason=AsyncMock())
    rack = Mock(execute=AsyncMock())
    with pytest.raises(PythonProbePreflightError) as caught:
        StrictTddLiveRunCompositionFactory().build(StrictTddLiveRunCompositionRequest(
            configuration(tmp_path), reasoning_gateway=reasoning, execution_gateway=rack,
        ))
    assert caught.value.diagnostic.kind == "infrastructure"
    assert caught.value.diagnostic.facts
    compose.assert_not_called()
    live_reasoning.assert_not_called()
    reasoning.reason.assert_not_called()
    rack.execute.assert_not_called()
    assert not (tmp_path / "repository").exists()
    assert not (tmp_path / "state" / "features").exists()
    assert not (tmp_path / "state" / "runs").exists()
    assert not (tmp_path / "state" / "revisions").exists()
    child.assert_called_once()


def test_successful_preflight_precedes_normal_composition(tmp_path, monkeypatch):
    events = []
    real = PythonPytestPreflight()
    def check(parent):
        result = real.check(parent)
        assert result.kind == "green"
        events.append("preflight")
        return result
    preflight = Mock(check=Mock(side_effect=check))
    application = Mock()
    def compose(request):
        events.append("compose")
        return Mock(application=application)
    monkeypatch.setattr("core.development.strict_tdd_live_run_composition.StrictTddFeatureCompositionFactory.build", Mock(side_effect=compose))
    reasoning = Mock(reason=AsyncMock())
    rack = Mock(execute=AsyncMock())
    composition = StrictTddLiveRunCompositionFactory(preflight=preflight).build(StrictTddLiveRunCompositionRequest(
        configuration(tmp_path), reasoning_gateway=reasoning, execution_gateway=rack,
    ))
    assert events == ["preflight", "compose"]
    assert composition.controller.application is application
    reasoning.reason.assert_not_called()
    rack.execute.assert_not_called()


def test_cli_reports_typed_preflight_blocker_without_starting_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("core.development.python_pytest_adapter.subprocess.run", Mock(
        return_value=subprocess.CompletedProcess([], 1, "", "pytest startup failure"),
    ))
    compose = Mock(side_effect=AssertionError("No model-backed stages"))
    monkeypatch.setattr("core.development.strict_tdd_live_run_composition.StrictTddFeatureCompositionFactory.build", compose)
    result = main([
        "start", "--run-id", "failed-preflight", "--project-id", "target", "--requirement", "Missing behavior",
        "--language", "python", "--test-framework", "pytest", "--production-path", "module.py",
        "--test-path", "tests/test_module.py", "--state-root", str(tmp_path / "state"),
        "--evidence-root", str(tmp_path / "evidence"),
    ])
    report = json.loads(capsys.readouterr().out)
    assert result == 2
    assert report["status"] == "blocked"
    assert report["blocked_reason"] == "python_pytest_preflight_failed"
    assert report["diagnostic"]["kind"] == "infrastructure"
    compose.assert_not_called()
    assert not (tmp_path / "state" / "runs").exists()
