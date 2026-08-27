"""Strict Rack AI work-unit v1 mapping."""

from __future__ import annotations

from dataclasses import dataclass

from core.development.work_unit import DevelopmentWorkUnit, ExecutionAttempt


CONTRACT_VERSION = "rack-ai/work-unit/v1"


@dataclass(frozen=True)
class RepositoryBinding:
    repository_id: str
    base_ref: str
    base_sha: str


def to_rack_ai_request(workload_id: str, binding: RepositoryBinding, unit: DevelopmentWorkUnit) -> dict:
    return {
        "version": CONTRACT_VERSION,
        "workload": {"id": workload_id, "kind": "application-development"},
        "repository": {
            "id": binding.repository_id,
            "base_ref": binding.base_ref,
            "base_sha": binding.base_sha,
        },
        "work_unit": {
            "id": unit.id,
            "objective": unit.objective,
            "allowed_paths": list(unit.allowed_paths),
            "acceptance": {
                "commands": [list(command) for command in unit.acceptance.commands],
                "required_artifacts": list(unit.acceptance.required_artifacts),
            },
            "readiness": {"ready": True, "depends_on": list(unit.depends_on)},
            "requirements": {
                "capability": unit.capability,
                "complexity": unit.complexity,
                "requires_large_context": unit.requires_large_context,
            },
            "limits": {
                "max_implementation_attempts": unit.max_implementation_attempts,
                "timeout_seconds": unit.timeout_seconds,
                "network": unit.network,
            },
        },
    }


def parse_rack_ai_result(payload: dict) -> ExecutionAttempt:
    verdict = str(payload.get("acceptance_verdict") or "").lower()
    return ExecutionAttempt(
        work_unit_id=payload["work_unit_id"],
        accepted=verdict == "approved",
        status=str(payload.get("status", "unknown")),
        change_id=payload.get("change_id"),
        selected_worker_id=payload.get("selected_worker_id"),
        placement=payload.get("placement"),
        branch=payload.get("branch"),
        accepted_revision=payload.get("accepted_head_sha") or payload.get("head_sha"),
        packet_path=payload.get("packet_path"),
        error=payload.get("last_error"),
    )
