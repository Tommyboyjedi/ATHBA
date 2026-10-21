from pathlib import Path
from dataclasses import replace
import subprocess

import core.development.deterministic_regression as regression_module

from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION,
    REGRESSION_CLEAR,
    REGRESSION_INFRASTRUCTURE_FAILURE,
    DEADLINE_NOT_EXECUTED,
    RUNTIME_TIMEOUT_SECONDS,
    RuntimeCommandRequest,
    SubprocessProjectRuntimeExecutor,
    DeterministicRegressionRequest,
    DeterministicRegressionService,
)
from core.development.microcycle_domain import RegressionCommandReport


class Runtime:
    def __init__(self, statuses):
        self.statuses = statuses
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        status = self.statuses.get(request.target, "passed")
        code = None if status == "infrastructure_failure" else (0 if status == "passed" else 1)
        return RegressionCommandReport(request.target, request.command, code, status, f"report/{request.target}")


def request():
    return DeterministicRegressionRequest(
        Path("/project"),
        ("python", "-m", "pytest", "-q"),
        "tests/test_current.py::test_current",
        ("tests/test_prior.py::test_prior",),
    )


def test_regression_runs_current_prior_then_accepted_suite_without_reasoning_gateway():
    runtime = Runtime({})
    result = DeterministicRegressionService(runtime).run(request())

    assert result.status == REGRESSION_CLEAR
    assert [item.target for item in runtime.requests] == [
        "tests/test_current.py::test_current",
        "tests/test_prior.py::test_prior",
        "accepted_regression_suite",
    ]
    assert runtime.requests[0].command[-1] == "tests/test_current.py::test_current"
    assert runtime.requests[-1].command == ("python", "-m", "pytest", "-q")


def test_regression_reports_only_newly_failing_prior_tests_for_repair_context():
    runtime = Runtime({"tests/test_prior.py::test_prior": "failed"})
    result = DeterministicRegressionService(runtime).run(request())

    assert result.status == ACCUMULATED_REGRESSION
    assert result.failing_prior_test_nodes == ("tests/test_prior.py::test_prior",)
    assert result.state(request().command).failing_prior_test_nodes == result.failing_prior_test_nodes


def test_regression_fails_closed_when_project_runtime_is_unavailable():
    runtime = Runtime({"tests/test_current.py::test_current": "infrastructure_failure"})

    result = DeterministicRegressionService(runtime).run(request())

    assert result.status == REGRESSION_INFRASTRUCTURE_FAILURE
    assert result.failing_prior_test_nodes == ()


def test_default_regression_preserves_timeout_and_does_not_read_deadline_clock(monkeypatch):
    def unexpected_clock():
        raise AssertionError("default regression must not consult a deadline clock")

    monkeypatch.setattr(regression_module.time, "monotonic", unexpected_clock)
    runtime = Runtime({})
    result = DeterministicRegressionService(runtime).run(request())

    assert result.status == REGRESSION_CLEAR
    assert len(runtime.requests) == 3
    assert all(item.timeout_seconds == RUNTIME_TIMEOUT_SECONDS for item in runtime.requests)


def test_deadline_bounds_each_command_by_remaining_shared_budget(monkeypatch):
    readings = iter((100.0, 125.0, 149.0))
    monkeypatch.setattr(regression_module.time, "monotonic", lambda: next(readings))
    runtime = Runtime({})

    result = DeterministicRegressionService(runtime).run(replace(request(), deadline=150.0))

    assert result.status == REGRESSION_CLEAR
    assert [item.timeout_seconds for item in runtime.requests] == [50.0, 25.0, 1.0]
    assert len(result.reports) == 3


def test_deadline_never_increases_existing_per_command_limit(monkeypatch):
    monkeypatch.setattr(regression_module.time, "monotonic", lambda: 100.0)
    runtime = Runtime({})

    result = DeterministicRegressionService(runtime).run(replace(request(), deadline=1000.0))

    assert result.status == REGRESSION_CLEAR
    assert [item.timeout_seconds for item in runtime.requests] == [RUNTIME_TIMEOUT_SECONDS] * 3


def test_expired_shared_budget_skips_remaining_commands_and_cannot_report_clear(monkeypatch):
    readings = iter((0.0, 61.0))
    monkeypatch.setattr(regression_module.time, "monotonic", lambda: next(readings))
    runtime = Runtime({})

    result = DeterministicRegressionService(runtime).run(replace(request(), deadline=60.0))

    assert result.status == REGRESSION_INFRASTRUCTURE_FAILURE
    assert len(runtime.requests) == 1
    assert runtime.requests[0].target == request().current_frontier_test
    assert len(result.reports) == 2
    assert result.reports[-1].target == request().prior_completed_test_nodes[0]
    assert result.reports[-1].return_code is None
    assert result.reports[-1].evidence_ref == DEADLINE_NOT_EXECUTED
    assert result.failing_prior_test_nodes == ()


def test_already_expired_deadline_executes_no_commands(monkeypatch):
    monkeypatch.setattr(regression_module.time, "monotonic", lambda: 100.0)
    runtime = Runtime({})

    result = DeterministicRegressionService(runtime).run(replace(request(), deadline=100.0))

    assert result.status == REGRESSION_INFRASTRUCTURE_FAILURE
    assert runtime.requests == []
    assert len(result.reports) == 1
    assert result.reports[0].evidence_ref == DEADLINE_NOT_EXECUTED


def test_subprocess_executor_uses_supplied_bounded_timeout(monkeypatch):
    observed = []

    def run(command, **kwargs):
        observed.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "passed", "")

    monkeypatch.setattr(regression_module.subprocess, "run", run)
    command = RuntimeCommandRequest(Path("/project"), "test", ("runner", "test"), 2.5)

    result = SubprocessProjectRuntimeExecutor().execute(command)

    assert result.status == "passed"
    assert observed[0][1]["timeout"] == 2.5


def test_subprocess_deadline_timeout_remains_infrastructure_failure(monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(regression_module.subprocess, "run", run)
    command = RuntimeCommandRequest(Path("/project"), "test", ("runner", "test"), 0.5)

    result = SubprocessProjectRuntimeExecutor().execute(command)

    assert result.status == "infrastructure_failure"
    assert result.return_code is None
    assert "0.5" in result.evidence_ref
