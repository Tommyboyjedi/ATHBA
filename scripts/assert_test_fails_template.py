import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from dataclasses import asdict, dataclass, field

PROBE_MARKER = "athba_red_probe_v1"
PHASES = ("setup", "call", "teardown")
PHASE_OUTCOMES = {"passed", "failed", "skipped", "not_run"}
PYTEST_OUTCOMES = {"failed", "passed", "skipped", "xfailed", "xpassed", "error", "not_run"}


@dataclass
class ProbeState:
    pytest_runtime_available: bool
    collection_succeeded: bool
    requested_node_found: bool
    requested_node_executed: bool
    outcome: str
    reported_node_id: str | None = None
    collected_node_ids: list[str] = field(default_factory=list)
    setup_outcome: str = "not_run"
    call_outcome: str = "not_run"
    teardown_outcome: str = "not_run"
    was_xfail: bool = False
    was_xpass: bool = False
    failure_phase: str | None = None
    exception_type: str | None = None
    failure_message: str | None = None
    traceback_location: str | None = None
    stdout: str = ""
    stderr: str = ""
    evidence_refs: list[str] = field(default_factory=list)


class StructuredPytestProbePlugin:
    def __init__(self, test_node: str):
        self.test_node = test_node
        self.state = ProbeState(
            pytest_runtime_available=True,
            collection_succeeded=True,
            requested_node_found=False,
            requested_node_executed=False,
            outcome="not_run",
            evidence_refs=[test_node],
        )

    def pytest_collection_finish(self, session) -> None:
        self.state.collected_node_ids = [item.nodeid for item in session.items]
        self.state.requested_node_found = self.test_node in self.state.collected_node_ids

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.state.collection_succeeded = False
            self._capture_failure("collection", report)

    @staticmethod
    def pytest_report_teststatus(report, config):
        return None

    def pytest_runtest_logreport(self, report) -> None:
        if report.nodeid != self.test_node:
            return
        self.state.reported_node_id = report.nodeid
        self.state.requested_node_found = True
        self.state.requested_node_executed = True
        if report.when in PHASES and report.outcome in PHASE_OUTCOMES:
            setattr(self.state, f"{report.when}_outcome", report.outcome)
        wasxfail = getattr(report, "wasxfail", None)
        if wasxfail and report.outcome == "skipped":
            self.state.was_xfail = True
        if wasxfail and report.outcome == "passed":
            self.state.was_xpass = True
        if report.failed or report.skipped or wasxfail:
            self._capture_failure(report.when, report)

    def finalize(self, exit_code: int) -> ProbeState:
        self.state.outcome = self._resolve_outcome(exit_code)
        return self.state

    def _resolve_outcome(self, exit_code: int) -> str:
        if self.state.was_xpass:
            return "xpassed"
        if self.state.was_xfail:
            return "xfailed"
        if not self.state.collection_succeeded:
            return "error"
        if self.state.call_outcome == "failed":
            return "failed"
        if self.state.setup_outcome == "failed" or self.state.teardown_outcome == "failed":
            return "error"
        if self.state.call_outcome == "passed":
            return "passed"
        if "skipped" in {self.state.setup_outcome, self.state.call_outcome, self.state.teardown_outcome}:
            return "skipped"
        if exit_code != 0:
            return "error"
        return "not_run"

    def _capture_failure(self, phase: str, report) -> None:
        if self.state.failure_phase is None:
            self.state.failure_phase = phase
        reprcrash = getattr(report.longrepr, "reprcrash", None)
        if reprcrash is not None:
            location = f"{reprcrash.path}:{reprcrash.lineno}"
            self.state.traceback_location = self.state.traceback_location or location
            message = getattr(reprcrash, "message", None)
            if message:
                self.state.failure_message = self.state.failure_message or message
                prefix = message.split(":", 1)[0].strip()
                if prefix:
                    self.state.exception_type = self.state.exception_type or prefix
        if self.state.failure_message is None:
            longrepr_text = str(report.longrepr).strip()
            if longrepr_text:
                self.state.failure_message = longrepr_text.splitlines()[-1]
        if self.state.exception_type is None and self.state.failure_message:
            prefix = self.state.failure_message.split(":", 1)[0].strip()
            if prefix and prefix[0].isalpha():
                self.state.exception_type = prefix


def _main() -> int:
    test_node = sys.argv[1]
    try:
        import pytest
    except ImportError:
        state = ProbeState(
            pytest_runtime_available=False,
            collection_succeeded=False,
            requested_node_found=False,
            requested_node_executed=False,
            outcome="not_run",
            failure_phase="collection",
            exception_type="ImportError",
            failure_message="pytest is unavailable",
            evidence_refs=[test_node],
        )
        print(f"{PROBE_MARKER} {json.dumps(asdict(state), sort_keys=True)}")
        return 0

    cwd = str(Path.cwd())
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    plugin = StructuredPytestProbePlugin(test_node)
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    command = ["-q", "-p", "no:cacheprovider", test_node]
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = pytest.main(command, plugins=[plugin])
    state = plugin.finalize(int(exit_code))
    state.stdout = stdout_buffer.getvalue()
    state.stderr = stderr_buffer.getvalue()
    print(f"{PROBE_MARKER} {json.dumps(asdict(state), sort_keys=True)}")
    return 0


raise SystemExit(_main())
