"""Strict Rack AI work-unit v1 mapping."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from core.development.work_unit import DevelopmentWorkUnit, ExecutionAttempt


CONTRACT_VERSION = "rack-ai/work-unit/v1"
WORKLOAD_KIND = "application-development"
SUPPORTED_ACCEPTANCE_VERDICTS = {"approved", "rejected"}
FORBIDDEN_RESOURCE_SELECTION_KEYS = {
    "backend",
    "backends",
    "device",
    "device_id",
    "endpoint",
    "endpoint_id",
    "endpoint_url",
    "gpu",
    "gpu_id",
    "gpu_ids",
    "model",
    "model_id",
    "model_ids",
    "port",
    "resource_ids",
    "selected_worker",
    "selected_worker_id",
    "worker",
    "worker_id",
    "worker_ids",
}


@dataclass(frozen=True)
class RepositoryBinding:
    repository_id: str
    base_ref: str
    base_sha: str | None = None
    registered_root: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.repository_id, "repository id")
        _require_text(self.base_ref, "base ref")
        if self.base_sha is not None:
            _require_text(self.base_sha, "base sha")
        if self.registered_root is not None:
            _require_text(self.registered_root, "registered root")

    def with_base_sha(self, base_sha: str | None) -> "RepositoryBinding":
        if base_sha is None:
            return replace(self, base_sha=None)
        _require_text(base_sha, "base sha")
        return replace(self, base_sha=base_sha)


def to_rack_ai_request(workload_id: str, binding: RepositoryBinding, unit: DevelopmentWorkUnit) -> dict[str, Any]:
    _require_text(workload_id, "workload id")
    if not unit.is_ready_for_execution():
        raise ValueError("work unit must be marked ready for execution before Rack AI submission")

    repository: dict[str, Any] = {
        "id": binding.repository_id,
        "base_ref": binding.base_ref,
    }
    if binding.base_sha is not None:
        repository["base_sha"] = binding.base_sha
    if binding.registered_root is not None:
        repository["registered_root"] = binding.registered_root

    return {
        "version": CONTRACT_VERSION,
        "workload": {"id": workload_id, "kind": WORKLOAD_KIND},
        "repository": repository,
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


def parse_rack_ai_result(payload: Mapping[str, Any]) -> ExecutionAttempt:
    work_unit_id = _required_string(payload, "work_unit_id")
    change_id = _required_string(payload, "change_id")
    status = _required_string(payload, "status")
    verdict = _required_string(payload, "acceptance_verdict").lower()
    if verdict not in SUPPORTED_ACCEPTANCE_VERDICTS:
        raise ValueError(f"unsupported Rack AI acceptance verdict: {verdict}")

    accepted = verdict == "approved"
    accepted_revision = None
    if accepted:
        accepted_revision = _optional_string(payload, "accepted_head_sha") or _optional_string(
            payload,
            "accepted_revision",
        )

    return ExecutionAttempt(
        work_unit_id=work_unit_id,
        accepted=accepted,
        status=status,
        change_id=change_id,
        selected_worker_id=_optional_string(payload, "selected_worker_id"),
        placement=_optional_mapping(payload.get("placement"), "placement"),
        branch=_optional_string(payload, "branch"),
        accepted_revision=accepted_revision,
        packet_path=_optional_string(payload, "packet_path"),
        worktree_path=_optional_string(payload, "worktree_path"),
        error=_optional_string(payload, "last_error"),
    )


def find_forbidden_resource_selection_keys(
    payload: Any,
    forbidden_keys: set[str] | None = None,
) -> list[str]:
    keys = forbidden_keys or FORBIDDEN_RESOURCE_SELECTION_KEYS
    matches: list[str] = []
    _walk_payload(payload, keys, matches, path="")
    return matches


def _walk_payload(payload: Any, forbidden_keys: set[str], matches: list[str], path: str) -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_name = str(key)
            child_path = f"{path}.{key_name}" if path else key_name
            if key_name.lower() in forbidden_keys:
                matches.append(child_path)
            _walk_payload(value, forbidden_keys, matches, child_path)
        return
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, value in enumerate(payload):
            child_path = f"{path}[{index}]"
            _walk_payload(value, forbidden_keys, matches, child_path)


def _required_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = _optional_string(payload, field_name)
    if value is None:
        raise ValueError(f"Rack AI result missing required field: {field_name}")
    return value


def _optional_string(payload: Mapping[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Rack AI field must be a non-empty string: {field_name}")
    return value


def _optional_mapping(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"Rack AI field must be an object: {field_name}")
    return dict(value)


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")
