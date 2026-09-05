"""Isolated structured pytest probe used by the Python adapter."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.development.python_missing_member import MissingMemberContext, missing_production_member


@dataclass
class _Facts:
    collection_succeeded: bool = True
    requested_node_found: bool = False
    requested_node_executed: bool = False
    outcome: str = "not_run"
    setup_outcome: str = "not_run"
    call_outcome: str = "not_run"
    teardown_outcome: str = "not_run"
    was_xfail: bool = False
    was_xpass: bool = False
    missing_production_member: bool = False
    exception_type: str | None = None
    failure_message: str | None = None
    source_line: int | None = None
    traceback_location: str | None = None
    stdout: str = ""
    stderr: str = ""
    evidence_refs: list[str] = field(default_factory=list)


class _Plugin:
    def __init__(self, node: str, production_path: str):
        self.node = node
        self.member_context = MissingMemberContext(Path(node.split("::", 1)[0]).resolve(), Path(production_path).resolve() if production_path else None)
        self.facts = _Facts(evidence_refs=[node])

    def pytest_runtest_makereport(self, item, call) -> None:
        if item.nodeid == self.node and call.when == "call" and call.excinfo is not None:
            self.facts.missing_production_member = missing_production_member(call.excinfo.value, self.member_context)

    def pytest_collection_finish(self, session) -> None:
        self.facts.requested_node_found = self.node in [item.nodeid for item in session.items]

    def pytest_collectreport(self, report) -> None:
        if report.failed:
            self.facts.collection_succeeded = False
            self._failure(report)

    def pytest_runtest_logreport(self, report) -> None:
        if report.nodeid != self.node:
            return
        self.facts.requested_node_found = True
        self.facts.requested_node_executed = True
        setattr(self.facts, f"{report.when}_outcome", report.outcome)
        marker = getattr(report, "wasxfail", None)
        self.facts.was_xfail = bool(marker and report.outcome == "skipped")
        self.facts.was_xpass = bool(marker and report.outcome == "passed")
        if report.failed or report.skipped or marker:
            self._failure(report)
        self.facts.stdout = self.facts.stdout or getattr(report, "capstdout", "")
        self.facts.stderr = self.facts.stderr or getattr(report, "capstderr", "")

    def _failure(self, report) -> None:
        crash = getattr(report.longrepr, "reprcrash", None)
        if crash is not None:
            self.facts.traceback_location = f"{crash.path}:{crash.lineno}"
            self.facts.source_line = crash.lineno
            self.facts.failure_message = crash.message
        text = str(report.longrepr)
        self.facts.failure_message = self.facts.failure_message or text.splitlines()[-1]
        match = re.findall(r":(\d+):", text)
        if self.facts.source_line is None and match:
            self.facts.source_line = int(match[-1])
        self.facts.exception_type = self.facts.exception_type or self.facts.failure_message.split(":", 1)[0].strip()

    def finish(self, exit_code: int) -> _Facts:
        if self.facts.was_xpass:
            self.facts.outcome = "xpassed"
        elif self.facts.was_xfail:
            self.facts.outcome = "xfailed"
        elif not self.facts.collection_succeeded or self.facts.setup_outcome == "failed" or self.facts.teardown_outcome == "failed":
            self.facts.outcome = "error"
        elif self.facts.call_outcome == "failed":
            self.facts.outcome = "failed"
        elif self.facts.call_outcome == "passed":
            self.facts.outcome = "passed"
        elif exit_code:
            self.facts.outcome = "error"
        return self.facts


def main() -> int:
    root, node, production_path = sys.argv[1:4]
    os.chdir(root)
    sys.path.insert(0, root)
    import pytest
    plugin = _Plugin(node, production_path)
    exit_code = pytest.main(["-q", "-p", "no:cacheprovider", node], plugins=[plugin])
    print(json.dumps(asdict(plugin.finish(int(exit_code)))), flush=True)
    return 0


raise SystemExit(main())
