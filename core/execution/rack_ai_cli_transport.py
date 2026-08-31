"""Process transport for Rack AI CLI change execution."""

from __future__ import annotations

import asyncio
import json
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.execution.rack_ai_request import RackAiChangeRequest
from core.filesystem_policy import resolve_confined_absolute_path


RackAiCliTransportError = RuntimeError
DEFAULT_CLI_CLEANUP_ALLOWANCE_SECONDS = 30
DEFAULT_CLI_TERMINATION_GRACE_SECONDS = 5


@dataclass(frozen=True)
class RackAiCliConfig:
    executable: str = "cargo"
    rack_ai_root: str = "/srv/rack-ai"
    state_root: str = "/srv/rack-ai"


@dataclass(frozen=True)
class RackAiCliProcessResult:
    stdout_text: str
    stderr_text: str
    returncode: int


@dataclass(frozen=True)
class RackAiCliSummary:
    packet_path: Path
    change_id: str | None = None
    branch: str | None = None
    worktree: str | None = None
    status: str | None = None
    acceptance_verdict: str | None = None
    base_sha: str | None = None


@dataclass(frozen=True)
class RackAiCliResponse:
    process: RackAiCliProcessResult
    summary: RackAiCliSummary
    packet_payload: dict[str, Any]


@dataclass(frozen=True)
class RackAiCliWatchdog:
    cleanup_allowance_seconds: int = DEFAULT_CLI_CLEANUP_ALLOWANCE_SECONDS
    termination_grace_seconds: int = DEFAULT_CLI_TERMINATION_GRACE_SECONDS

    def __post_init__(self) -> None:
        if self.cleanup_allowance_seconds < 0:
            raise ValueError("cleanup allowance seconds must be non-negative")
        if self.termination_grace_seconds <= 0:
            raise ValueError("termination grace seconds must be positive")

    def deadline_seconds(self, request: RackAiChangeRequest) -> int:
        return max(1, request.limits.timeout_seconds + self.cleanup_allowance_seconds)

    async def communicate(
        self,
        process: asyncio.subprocess.Process,
        request: RackAiChangeRequest,
    ) -> RackAiCliProcessResult:
        task = asyncio.create_task(process.communicate())
        deadline_seconds = self.deadline_seconds(request)
        try:
            stdout, stderr = await asyncio.wait_for(asyncio.shield(task), timeout=deadline_seconds)
            return _process_result(stdout, stderr, process.returncode)
        except asyncio.TimeoutError as error:
            result = await self._terminate_and_reap(process, task)
            message = (
                "Rack AI CLI subprocess exceeded ATHBA transport deadline "
                f"of {deadline_seconds}s for request timeout {request.limits.timeout_seconds}s"
            )
            raise RackAiCliTransportError(_build_error_message(message, result)) from error

    async def _terminate_and_reap(
        self,
        process: asyncio.subprocess.Process,
        task: asyncio.Task[tuple[bytes, bytes]],
    ) -> RackAiCliProcessResult:
        _signal_process(process, terminate=True)
        try:
            stdout, stderr = await asyncio.wait_for(asyncio.shield(task), timeout=self.termination_grace_seconds)
            return _process_result(stdout, stderr, process.returncode)
        except asyncio.TimeoutError:
            _signal_process(process, terminate=False)
            try:
                stdout, stderr = await asyncio.wait_for(asyncio.shield(task), timeout=self.termination_grace_seconds)
            except asyncio.TimeoutError as error:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                raise RackAiCliTransportError(
                    "Rack AI CLI timeout cleanup failed after terminate/kill"
                ) from error
            return _process_result(stdout, stderr, process.returncode)


class RackAiCliCommandFactory:
    def __init__(self, config: RackAiCliConfig):
        self.config = config

    def build(self, spec_path: Path) -> tuple[str, ...]:
        return (
            self.config.executable,
            "run",
            "-q",
            "-p",
            "rack_ai_cli",
            "--",
            "change",
            str(spec_path),
            "--repo-root",
            self.config.rack_ai_root,
            "--state-root",
            self.config.state_root,
        )


class RackAiCliSummaryParser:
    def parse(self, text: str) -> RackAiCliSummary:
        summary: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            key, separator, value = line.partition(":")
            if not separator:
                continue
            summary[key.strip()] = value.strip()
        if not summary:
            raise ValueError("Rack AI command summary was empty")
        packet = summary.get("packet")
        if packet is None or not packet.strip():
            raise ValueError("Rack AI command summary missing field: packet")
        return RackAiCliSummary(
            packet_path=Path(packet),
            change_id=summary.get("change_id"),
            branch=summary.get("branch"),
            worktree=summary.get("worktree"),
            status=summary.get("status"),
            acceptance_verdict=summary.get("acceptance_verdict"),
            base_sha=summary.get("base_sha"),
        )


class RackAiPacketLoader:
    def __init__(self, state_root: str | Path):
        self.state_root = Path(state_root).resolve()

    def load(self, path: Path) -> dict[str, Any]:
        packet_path = resolve_confined_absolute_path(self.state_root, path, "Rack AI packet path")
        return json.loads(packet_path.read_text(encoding="utf-8"))


class RackAiCliTransport:
    def __init__(self, config: RackAiCliConfig):
        self.config = config
        self.commands = RackAiCliCommandFactory(config)
        self.summary_parser = RackAiCliSummaryParser()
        self.packet_loader = RackAiPacketLoader(config.state_root)
        self.watchdog = RackAiCliWatchdog()

    async def execute(self, request: RackAiChangeRequest) -> RackAiCliResponse:
        spec_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
                json.dump(request.to_dict(), handle)
                handle.flush()
                spec_path = Path(handle.name)
            process = await asyncio.create_subprocess_exec(
                *self.commands.build(spec_path),
                cwd=self.config.rack_ai_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            result = await self.watchdog.communicate(process, request)
            if not result.stdout_text.strip():
                fallback = _response_from_expected_packet(self.packet_loader, self.config, request, result)
                if fallback is not None:
                    return fallback
                raise RackAiCliTransportError(_build_error_message("Rack AI returned no command summary", result))
            summary = self.summary_parser.parse(result.stdout_text)
            packet = self.packet_loader.load(summary.packet_path)
            return RackAiCliResponse(result, summary, packet)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            if isinstance(error, RackAiCliTransportError):
                raise
            process = RackAiCliProcessResult("", "", 0) if "result" not in locals() else result
            raise RackAiCliTransportError(
                _build_error_message(f"Rack AI returned untrustworthy output: {error}", process)
            ) from error
        finally:
            if spec_path is not None:
                spec_path.unlink(missing_ok=True)


def _response_from_expected_packet(
    packet_loader: RackAiPacketLoader,
    config: RackAiCliConfig,
    request: RackAiChangeRequest,
    process: RackAiCliProcessResult,
) -> RackAiCliResponse | None:
    packet_path = Path(config.state_root) / "state" / "changes" / request.change_id / "review-packet.json"
    if not packet_path.exists():
        return None
    packet = packet_loader.load(packet_path)
    return RackAiCliResponse(
        process=process,
        summary=RackAiCliSummary(
            packet_path=packet_path,
            change_id=request.change_id,
            branch=_optional_packet_string(packet, "branch"),
            worktree=_optional_packet_string(packet, "worktree_path"),
            status=_optional_packet_string(packet, "status"),
            acceptance_verdict=_optional_packet_string(packet, "acceptance_verdict"),
            base_sha=_optional_packet_string(packet, "base_sha"),
        ),
        packet_payload=packet,
    )


def _optional_packet_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _signal_process(process: asyncio.subprocess.Process, *, terminate: bool) -> None:
    try:
        if process.returncode is not None:
            return
        if terminate:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        return


def _process_result(stdout: bytes, stderr: bytes, returncode: int | None) -> RackAiCliProcessResult:
    code = 0 if returncode is None else returncode
    return RackAiCliProcessResult(
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
        code,
    )


def _build_error_message(message: str, process: RackAiCliProcessResult) -> str:
    parts = [message]
    if process.stderr_text.strip():
        parts.append(f"stderr: {process.stderr_text.strip()}")
    if process.stdout_text.strip():
        parts.append(f"stdout: {process.stdout_text.strip()}")
    return " | ".join(parts)
