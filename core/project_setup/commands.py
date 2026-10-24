"""Bounded argv execution for controlled setup profiles, never model-authored shell."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import os
import subprocess

from core.project_setup.profile_domain import ToolProbe


@dataclass(frozen=True)
class SetupCommand:
    argv: tuple[str, ...]
    cwd: Path


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ToolObservation:
    kind: str
    expected_version: str
    actual_version: str | None
    available: bool
    result: CommandResult


@dataclass(frozen=True)
class SetupCommandPolicy:
    timeout_seconds: float = 30.0


class SetupCommandRunner:
    def __init__(self, policy: SetupCommandPolicy | None = None):
        self.policy = policy or SetupCommandPolicy()

    def run(self, request: SetupCommand) -> CommandResult:
        try:
            result = subprocess.run(
                request.argv, cwd=request.cwd, capture_output=True, text=True,
                timeout=self.policy.timeout_seconds, check=False,
                env=os.environ | {"RUSTUP_AUTO_INSTALL": "0", "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
                                  "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "NPM_CONFIG_UPDATE_NOTIFIER": "false",
                                  "COREPACK_ENABLE_NETWORK": "0", "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0",
                                  "npm_config_offline": "true",
                                  "DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE": "true",
                                  "DOTNET_CLI_WORKLOAD_MANIFEST_UPDATE_DISABLE": "true"},
            )
            return CommandResult(request.argv, result.returncode, result.stdout, result.stderr)
        except (OSError, subprocess.TimeoutExpired) as error:
            return CommandResult(request.argv, None, "", type(error).__name__ + ": " + str(error))

    def inspect(self, request: tuple[ToolProbe, Path]) -> ToolObservation:
        probe, cwd = request
        result = self.run(SetupCommand(probe.argv, cwd))
        versions = re.findall(r"\b\d+\.\d+(?:\.\d+){0,2}(?:[-+][A-Za-z0-9.-]+|[a-zA-Z][A-Za-z0-9.-]*)?", result.stdout + result.stderr)
        actual = (probe.tool.version if "--list-sdks" in probe.argv and probe.tool.version in versions
                  else versions[0] if versions else None)
        return ToolObservation(probe.tool.kind.value, probe.tool.version, actual,
                               result.returncode == 0 and actual == probe.tool.version, result)
