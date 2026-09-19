"""Rack AI CLI transport used only behind the generic workspace connector."""
from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.filesystem_policy import resolve_confined_absolute_path
CLI_CLEANUP_ALLOWANCE_SECONDS = 30


@dataclass(frozen=True)
class RackAiWorkspaceCliConfig:
    executable: str = "cargo"
    rack_ai_root: str = "/srv/rack-ai"
    state_root: str = "/srv/rack-ai"

@dataclass(frozen=True)
class RackAiWorkspaceCliInvocation:
    spec_path: Path
    payload: dict[str, object]
    routing: dict[str, object]


class RackAiWorkspaceCliTransport:
    """Runs the published v2 CLI and returns terminal packet facts to the connector."""

    def __init__(self, config: RackAiWorkspaceCliConfig):
        self.config = config

    def submit(self, payload: dict[str, object]) -> dict[str, object]:
        routing = _routing(payload)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            spec_path = Path(handle.name)
        try:
            return self._run(RackAiWorkspaceCliInvocation(spec_path, payload, routing))
        finally:
            spec_path.unlink(missing_ok=True)

    def _run(self, invocation: RackAiWorkspaceCliInvocation) -> dict[str, object]:
        try:
            completed = subprocess.run(
                self._command(invocation.spec_path),
                cwd=self.config.rack_ai_root,
                capture_output=True,
                check=False,
                text=True,
                timeout=_timeout_seconds(invocation.payload),
            )
        except subprocess.TimeoutExpired:
            return _terminal(invocation.routing, "timeout", "Rack AI CLI transport timed out")
        if completed.stdout.strip():
            return self._packet_result(completed.stdout, invocation.routing)
        return _failure_result(invocation.routing, completed.stderr)

    def _command(self, spec_path: Path) -> tuple[str, ...]:
        return (
            self.config.executable,
            "run",
            "-q",
            "-p",
            "rack_ai_cli",
            "--",
            "work-unit",
            "--emit-json",
            str(spec_path),
            "--repo-root",
            self.config.rack_ai_root,
            "--state-root",
            self.config.state_root,
        )

    def _packet_result(self, stdout: str, routing: dict[str, object]) -> dict[str, object]:
        result = json.loads(stdout)
        if not isinstance(result, dict):
            return _terminal(routing, "backend_unavailable", "Rack AI CLI emitted a non-object result")
        packet_path = result.get("packet_path")
        if not isinstance(packet_path, str) or not packet_path.strip():
            return _terminal(routing, "backend_unavailable", "Rack AI CLI omitted the packet path")
        confined = resolve_confined_absolute_path(Path(self.config.state_root).resolve(), Path(packet_path), "Rack AI packet path")
        packet = json.loads(confined.read_text(encoding="utf-8"))
        if not isinstance(packet, dict):
            return _terminal(routing, "backend_unavailable", "Rack AI packet was not an object")
        packet["submission_id"] = routing["submission_id"]
        packet["packet_path"] = packet_path
        return packet


def _routing(payload: dict[str, object]) -> dict[str, object]:
    work_unit = payload.get("work_unit")
    if not isinstance(work_unit, dict):
        raise ValueError("Rack AI v2 work unit is missing")
    routing = work_unit.get("routing")
    if not isinstance(routing, dict):
        raise ValueError("Rack AI v2 routing header is missing")
    return routing


def _timeout_seconds(payload: dict[str, object]) -> int:
    work_unit = payload.get("work_unit")
    if not isinstance(work_unit, dict):
        raise ValueError("Rack AI v2 work unit is missing")
    limits = work_unit.get("limits")
    if not isinstance(limits, dict) or not isinstance(limits.get("timeout_seconds"), int):
        raise ValueError("Rack AI v2 timeout is missing")
    return limits["timeout_seconds"] + CLI_CLEANUP_ALLOWANCE_SECONDS


def _failure_result(routing: dict[str, object], stderr: str) -> dict[str, object]:
    message = stderr.strip() or "Rack AI CLI returned no terminal packet"
    if "duplicate idempotent submission" in message:
        return _terminal(routing, "duplicate_submission", message)
    if "temporarily unavailable" in message:
        return _terminal(routing, "temporarily_unavailable", message)
    if "capability" in message:
        return _terminal(routing, "capability_unavailable", message)
    return _terminal(routing, "backend_unavailable", message)


def _terminal(routing: dict[str, object], status: str, failure: str) -> dict[str, object]:
    return {"submission_id": routing["submission_id"], "status": status, "generic_failure": failure}
