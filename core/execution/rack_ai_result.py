"""Typed result mapping and policy scanning for Rack AI output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.development.work_unit import ExecutionAttempt


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
class RackAiGatewayResult:
    work_unit_id: str
    summary: object
    packet_payload: Mapping[str, Any]


@dataclass(frozen=True)
class ResourceScanState:
    forbidden_keys: set[str]
    matches: list[str]
    path: str = ""


class RackAiResultParser:
    def parse(self, payload: Mapping[str, Any]) -> ExecutionAttempt:
        work_unit_id = _required_string(payload, "work_unit_id")
        change_id = _required_string(payload, "change_id")
        status = _required_string(payload, "status")
        verdict = _required_string(payload, "acceptance_verdict").lower()
        if verdict not in SUPPORTED_ACCEPTANCE_VERDICTS:
            raise ValueError(f"unsupported Rack AI acceptance verdict: {verdict}")
        accepted = verdict == "approved"
        accepted_revision = None
        if accepted:
            accepted_revision = _optional_string(payload, "accepted_head_sha") or _optional_string(payload, "accepted_revision") or _optional_string(payload, "head_sha")
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
            worktree_path=_optional_string(payload, "worktree_path") or _optional_string(payload, "worktree"),
            error=_optional_string(payload, "last_error"),
        )


class RackAiExecutionResultMapper:
    def map(self, result: RackAiGatewayResult):
        from core.execution.work_unit_gateway import WorkUnitExecutionResult

        payload = {
            **dict(result.packet_payload),
            "work_unit_id": result.work_unit_id,
            "change_id": getattr(result.summary, "change_id") or result.packet_payload.get("change_id"),
            "branch": getattr(result.summary, "branch") or result.packet_payload.get("branch"),
            "worktree_path": getattr(result.summary, "worktree") or result.packet_payload.get("worktree_path"),
            "status": getattr(result.summary, "status") or result.packet_payload.get("status"),
            "acceptance_verdict": getattr(result.summary, "acceptance_verdict") or result.packet_payload.get("acceptance_verdict"),
            "packet_path": str(getattr(result.summary, "packet_path")),
        }
        attempt = RackAiResultParser().parse(payload)
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


class ForbiddenResourceSelectionScanner:
    def scan(self, payload: Any, forbidden_keys: set[str]) -> list[str]:
        matches: list[str] = []
        self._walk(payload, ResourceScanState(forbidden_keys, matches))
        return matches

    def _walk(self, payload: Any, state: ResourceScanState) -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                key_name = str(key)
                child_path = f"{state.path}.{key_name}" if state.path else key_name
                if key_name.lower() in state.forbidden_keys:
                    state.matches.append(child_path)
                self._walk(value, ResourceScanState(state.forbidden_keys, state.matches, child_path))
            return
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            for index, value in enumerate(payload):
                child_path = f"{state.path}[{index}]"
                self._walk(value, ResourceScanState(state.forbidden_keys, state.matches, child_path))


def parse_rack_ai_result(payload: Mapping[str, Any]) -> ExecutionAttempt:
    return RackAiResultParser().parse(payload)


def find_forbidden_resource_selection_keys(payload: Any, forbidden_keys: set[str] | None = None) -> list[str]:
    keys = FORBIDDEN_RESOURCE_SELECTION_KEYS if forbidden_keys is None else forbidden_keys
    return ForbiddenResourceSelectionScanner().scan(payload, keys)


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
