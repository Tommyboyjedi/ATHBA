"""Structured, non-LLM accumulated regression execution for strict microcycles."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.development.microcycle_domain import RegressionCommandReport, RegressionState

REGRESSION_CLEAR = "regression_clear"
ACCUMULATED_REGRESSION = "accumulated_regression"
REGRESSION_INFRASTRUCTURE_FAILURE = "regression_infrastructure_failure"
FULL_SUITE_TARGET = "accepted_regression_suite"
RUNTIME_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class RuntimeCommandRequest:
    project_root: Path
    target: str
    command: tuple[str, ...]


class ProjectRuntimeExecutor(Protocol):
    """Executes project commands and returns facts; it has no reasoning seam."""

    def execute(self, request: RuntimeCommandRequest) -> RegressionCommandReport: ...


class SubprocessProjectRuntimeExecutor:
    """Runs the configured project runtime without parsing LLM-produced prose."""

    def execute(self, request: RuntimeCommandRequest) -> RegressionCommandReport:
        try:
            completed = subprocess.run(
                request.command,
                cwd=request.project_root,
                capture_output=True,
                text=True,
                timeout=RUNTIME_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return RegressionCommandReport(
                request.target, request.command, None, "infrastructure_failure", str(error)
            )
        status = "passed" if completed.returncode == 0 else "failed"
        evidence = (completed.stderr or completed.stdout or f"returncode={completed.returncode}").strip()
        return RegressionCommandReport(request.target, request.command, completed.returncode, status, evidence)


@dataclass(frozen=True)
class DeterministicRegressionRequest:
    project_root: Path
    command: tuple[str, ...]
    current_frontier_test: str
    prior_completed_test_nodes: tuple[str, ...] = ()
    include_accepted_suite: bool = True

    def __post_init__(self) -> None:
        if not self.command or not self.current_frontier_test.strip():
            raise ValueError("regression request requires a command and current frontier")
        if any(not item.strip() for item in self.prior_completed_test_nodes):
            raise ValueError("prior completed test nodes must be non-empty")


@dataclass(frozen=True)
class DeterministicRegressionResult:
    status: str
    reports: tuple[RegressionCommandReport, ...]
    failing_prior_test_nodes: tuple[str, ...]

    def state(self, command: tuple[str, ...]) -> RegressionState:
        evidence = tuple(item.evidence_ref for item in self.reports)
        return RegressionState(self.status, command, evidence, self.reports, self.failing_prior_test_nodes)


class DeterministicRegressionService:
    """Runs current, protected prior, then accepted-suite checks in a fixed order."""

    def __init__(self, runtime: ProjectRuntimeExecutor):
        self.runtime = runtime

    def run(self, request: DeterministicRegressionRequest) -> DeterministicRegressionResult:
        reports = tuple(self.runtime.execute(item) for item in self._commands(request))
        if any(item.status == "infrastructure_failure" for item in reports):
            return DeterministicRegressionResult(REGRESSION_INFRASTRUCTURE_FAILURE, reports, ())
        failing = tuple(
            item.target for item in reports
            if item.target in request.prior_completed_test_nodes and item.status == "failed"
        )
        status = REGRESSION_CLEAR if all(item.status == "passed" for item in reports) else ACCUMULATED_REGRESSION
        return DeterministicRegressionResult(status, reports, failing)

    @staticmethod
    def _commands(request: DeterministicRegressionRequest) -> tuple[RuntimeCommandRequest, ...]:
        targets = (request.current_frontier_test, *request.prior_completed_test_nodes)
        checks = tuple(RuntimeCommandRequest(request.project_root, target, (*request.command, target)) for target in dict.fromkeys(targets))
        suite = (RuntimeCommandRequest(request.project_root, FULL_SUITE_TARGET, request.command),) if request.include_accepted_suite else ()
        return (*checks, *suite)
