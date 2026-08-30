"""Process transport for Rack AI CLI change execution."""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.execution.rack_ai_request import RackAiChangeRequest
from core.filesystem_policy import resolve_confined_absolute_path


RackAiCliTransportError = RuntimeError


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
            stdout, stderr = await process.communicate()
            result = RackAiCliProcessResult(
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
                process.returncode,
            )
            if not result.stdout_text.strip():
                raise RackAiCliTransportError(_build_error_message("Rack AI returned no command summary", result))
            summary = self.summary_parser.parse(result.stdout_text)
            packet = self.packet_loader.load(summary.packet_path)
            return RackAiCliResponse(result, summary, packet)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            if isinstance(error, RackAiCliTransportError):
                raise
            process = RackAiCliProcessResult("", "", 0) if "result" not in locals() else result
            raise RackAiCliTransportError(_build_error_message(f"Rack AI returned untrustworthy output: {error}", process)) from error
        finally:
            if spec_path is not None:
                spec_path.unlink(missing_ok=True)


def _build_error_message(message: str, process: RackAiCliProcessResult) -> str:
    parts = [message]
    if process.stderr_text.strip():
        parts.append(f"stderr: {process.stderr_text.strip()}")
    if process.stdout_text.strip():
        parts.append(f"stdout: {process.stdout_text.strip()}")
    return " | ".join(parts)
