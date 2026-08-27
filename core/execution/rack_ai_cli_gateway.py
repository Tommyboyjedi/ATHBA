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


@dataclass(frozen=True)
class RackAiCliConfig:
    executable: str = "cargo"
    rack_ai_root: str = "/srv/rack-ai"
    state_root: str = "/srv/rack-ai"


class RackAiCliExecutionGateway:
    """Invoke Rack AI without leaking worker/model/GPU choices into ATHBA."""

    def __init__(self, workload_id: str, binding: RepositoryBinding, config: RackAiCliConfig | None = None):
        self.workload_id = workload_id
        self.binding = binding
        self.config = config or RackAiCliConfig()

    async def execute(self, work_unit: DevelopmentWorkUnit) -> WorkUnitExecutionResult:
        payload = to_rack_ai_request(self.workload_id, self.binding, work_unit)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            spec_path = Path(handle.name)

        try:
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
            if not stdout:
                raise RuntimeError(stderr.decode("utf-8", errors="replace") or "Rack AI returned no JSON")
            attempt = parse_rack_ai_result(json.loads(stdout.decode("utf-8")))
            return WorkUnitExecutionResult(
                work_unit_id=attempt.work_unit_id,
                accepted=attempt.accepted,
                status=attempt.status,
                change_id=attempt.change_id,
                branch=attempt.branch,
                accepted_revision=attempt.accepted_revision,
                evidence_location=attempt.packet_path,
            )
        finally:
            spec_path.unlink(missing_ok=True)
