"""CLI adapter for Rack AI's machine-readable work-unit entry point."""

from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.development.work_unit import DevelopmentWorkUnit
from core.execution.rack_ai_contract import RepositoryBinding, parse_rack_ai_result, to_rack_ai_request
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class RackAiCliTransportError(RuntimeError):
    """Raised when Rack AI output cannot be trusted or interpreted safely."""


@dataclass(frozen=True)
class RackAiCliConfig:
    executable: str = "cargo"
    rack_ai_root: str = "/srv/rack-ai"
    state_root: str = "/srv/rack-ai"


class RackAiCliExecutionGateway:
    """Invoke Rack AI without leaking worker/model/GPU choices into ATHBA."""

    def __init__(self, workload_id: str, config: RackAiCliConfig | None = None):
        self.workload_id = workload_id
        self.config = config or RackAiCliConfig()

    async def execute(
        self,
        work_unit: DevelopmentWorkUnit,
        repository_binding: RepositoryBinding,
    ) -> WorkUnitExecutionResult:
        payload = to_rack_ai_request(self.workload_id, repository_binding, work_unit)
        spec_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
                json.dump(payload, handle)
                handle.flush()
                spec_path = Path(handle.name)

            process = await asyncio.create_subprocess_exec(
                self.config.executable,
                "run",
                "-q",
                "-p",
                "rack_ai_cli",
                "--",
                "work-unit",
                str(spec_path),
                "--repo-root",
                self.config.rack_ai_root,
                "--state-root",
                self.config.state_root,
                "--emit-json",
                cwd=self.config.rack_ai_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            if not stdout_text.strip():
                raise RackAiCliTransportError(_build_error_message("Rack AI returned no JSON", stderr_text))

            try:
                attempt = parse_rack_ai_result(json.loads(stdout_text))
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise RackAiCliTransportError(
                    _build_error_message(f"Rack AI returned untrustworthy output: {error}", stderr_text, stdout_text)
                ) from error

            return WorkUnitExecutionResult(
                work_unit_id=attempt.work_unit_id,
                accepted=attempt.accepted,
                status=attempt.status,
                change_id=attempt.change_id,
                selected_worker_id=attempt.selected_worker_id,
                placement=attempt.placement,
                branch=attempt.branch,
                accepted_revision=attempt.accepted_revision,
                evidence_location=attempt.packet_path,
                worktree_path=attempt.worktree_path,
                error=attempt.error,
            )
        finally:
            if spec_path is not None:
                spec_path.unlink(missing_ok=True)


def _build_error_message(message: str, stderr_text: str, stdout_text: str | None = None) -> str:
    parts = [message]
    if stderr_text.strip():
        parts.append(f"stderr: {stderr_text.strip()}")
    if stdout_text is not None and stdout_text.strip():
        parts.append(f"stdout: {stdout_text.strip()}")
    return " | ".join(parts)
