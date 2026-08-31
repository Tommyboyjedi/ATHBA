from pathlib import Path

from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION,
    REGRESSION_CLEAR,
    REGRESSION_INFRASTRUCTURE_FAILURE,
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
