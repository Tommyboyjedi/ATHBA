"""Zero-model readiness for the Python runtime used by strict-TDD probes."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from core.development.microcycle_domain import (
    BoundaryDiagnostic, DiagnosticFact, FragmentSourceSpan, FrontierExecutionRequest,
    MaterialisedTestArtifact, SourceSpan,
)
from core.development.python_pytest_adapter import PythonPytestAdapter

PREFLIGHT_TEST_PATH = "tests/test_probe_readiness.py"
PREFLIGHT_TEST_NODE = PREFLIGHT_TEST_PATH + "::test_probe_readiness"
PREFLIGHT_SOURCE = """def test_probe_readiness(pytestconfig):
    import os
    import sys
    from pathlib import Path
    target = Path(__file__).resolve().parents[1]
    assert pytestconfig.rootpath == target
    assert pytestconfig.inipath == Path(os.devnull)
    assert all(Path(entry).resolve() != Path({harness_root!r}) for entry in sys.path)
    assert 'DJANGO_SETTINGS_MODULE' not in os.environ
"""


class PythonProbePreflightError(Exception):
    """A typed harness blocker raised before composing any model-backed work."""

    def __init__(self, diagnostic: BoundaryDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


class PythonPytestPreflight:
    """Exercise the production probe on a disposable behavior-free target."""

    def check(self, workspace_parent: Path) -> BoundaryDiagnostic:
        try:
            workspace_parent.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix="pytest-preflight-", dir=workspace_parent) as directory:
                diagnostic = PythonPytestAdapter().execute_frontier(
                    FrontierExecutionRequest(self._artifact(), directory, PREFLIGHT_TEST_PATH)
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            return self._execution_failure(error)
        facts = {item.name: item.value for item in diagnostic.facts}
        expected = {
            "collection_succeeded": "True", "requested_node_found": "True", "requested_node_executed": "True",
            "outcome": "passed", "setup_outcome": "passed", "call_outcome": "passed", "teardown_outcome": "passed",
        }
        if diagnostic.kind == "green" and all(facts.get(name) == value for name, value in expected.items()):
            return diagnostic
        return BoundaryDiagnostic(
            "infrastructure", "Python/pytest target probe preflight failed",
            diagnostic.evidence_refs, (*diagnostic.facts, DiagnosticFact("preflight_diagnostic", json.dumps(diagnostic.to_dict()))),
        )

    @staticmethod
    def _artifact() -> MaterialisedTestArtifact:
        descriptor = PythonPytestAdapter.descriptor
        source = PREFLIGHT_SOURCE.format(harness_root=str(Path(__file__).resolve().parents[2]))
        return MaterialisedTestArtifact(
            descriptor.adapter_id, descriptor.adapter_version, "probe-readiness", 0, PREFLIGHT_TEST_NODE,
            source, "probe-readiness", (FragmentSourceSpan("probe-readiness", SourceSpan(2, len(source.splitlines()))),),
            "preflight-no-production-revision",
        )

    @staticmethod
    def _execution_failure(error: OSError | subprocess.TimeoutExpired) -> BoundaryDiagnostic:
        facts = [DiagnosticFact("probe_exception", type(error).__name__), DiagnosticFact("probe_error", str(error))]
        if isinstance(error, subprocess.TimeoutExpired):
            facts.append(DiagnosticFact("probe_command", json.dumps(error.cmd)))
            for name, output in (("probe_stdout", error.stdout), ("probe_stderr", error.stderr)):
                text = output.decode(errors="replace") if isinstance(output, bytes) else output
                facts.append(DiagnosticFact(name, json.dumps(text)))
        return BoundaryDiagnostic("infrastructure", "Python/pytest target probe could not execute", ("pytest-probe",), tuple(facts))
