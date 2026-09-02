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
class RackAiExpectedIdentity:
    work_unit_id: str
    change_id: str
    repository_id: str
    base_sha: str | None = None


@dataclass(frozen=True)
class RackAiGatewayResult:
    expected: RackAiExpectedIdentity
    summary: object
    packet_payload: Mapping[str, Any]
    process: object | None = None


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


class RackAiIdentityVerifier:
    def verify(self, result: RackAiGatewayResult) -> dict[str, Any]:
        packet = dict(result.packet_payload)
        summary = result.summary
        expected = result.expected
        _match_required(packet.get("change_id"), expected.change_id, "Rack AI packet change id")
        _match_required(packet.get("repository_id"), expected.repository_id, "Rack AI packet repository id")
        _match_optional(packet.get("base_sha"), expected.base_sha, "Rack AI packet base sha")
        _match_optional(getattr(summary, "change_id"), expected.change_id, "Rack AI summary change id")
        _match_optional(getattr(summary, "base_sha"), expected.base_sha, "Rack AI summary base sha")
        status = _coalesce(getattr(summary, "status"), packet.get("status"), "Rack AI status")
        verdict = _coalesce(
            getattr(summary, "acceptance_verdict"),
            packet.get("acceptance_verdict"),
            "Rack AI acceptance verdict",
        )
        branch = _coalesce_optional(getattr(summary, "branch"), packet.get("branch"), "Rack AI branch")
        worktree = _coalesce_optional(
            getattr(summary, "worktree"),
            packet.get("worktree_path") or packet.get("worktree"),
            "Rack AI worktree path",
        )
        return {
            **packet,
            "work_unit_id": expected.work_unit_id,
            "change_id": expected.change_id,
            "status": status,
            "acceptance_verdict": verdict,
            "branch": branch,
            "worktree_path": worktree,
            "packet_path": str(getattr(summary, "packet_path")),
        }


class RackAiExecutionResultMapper:
    def __init__(self):
        self.verifier = RackAiIdentityVerifier()
        self.parser = RackAiResultParser()

    def map(self, result: RackAiGatewayResult):
        from core.execution.work_unit_gateway import ExecutionPolicyEvidence, WorkUnitExecutionResult

        attempt = self.parser.parse(self.verifier.verify(result))
        process = result.process
        stdout = None if process is None else getattr(process, "stdout_text", None)
        stderr = None if process is None else getattr(process, "stderr_text", None)
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
            stdout=stdout,
            stderr=stderr,
            policy_evidence=_policy_evidence(result.packet_payload, ExecutionPolicyEvidence),
        )


def _policy_evidence(payload: Mapping[str, Any], evidence_type: type):
    allowed_paths = _optional_string_list(payload.get("allowed_paths"), "allowed_paths")
    changed_paths = _optional_string_list(payload.get("changed_paths"), "changed_paths")
    if allowed_paths is None and changed_paths is None:
        return None
    return evidence_type(
        allowed_paths=allowed_paths or [],
        changed_paths=changed_paths or [],
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


def _coalesce(summary_value: object, packet_value: object, label: str) -> str:
    _match_optional(summary_value, packet_value, label)
    if summary_value is not None:
        return _string_value(summary_value, label)
    if packet_value is not None:
        return _string_value(packet_value, label)
    raise ValueError(f"{label} is missing")


def _coalesce_optional(summary_value: object, packet_value: object, label: str) -> str | None:
    _match_optional(summary_value, packet_value, label)
    if summary_value is not None:
        return _string_value(summary_value, label)
    if packet_value is not None:
        return _string_value(packet_value, label)
    return None


def _match_required(actual: object, expected: str, label: str) -> None:
    if _string_value(actual, label) != expected:
        raise ValueError(f"{label} did not match the submitted request")


def _match_optional(actual: object, expected: object, label: str) -> None:
    if actual is None or expected is None:
        return
    if _string_value(actual, label) != _string_value(expected, label):
        raise ValueError(f"{label} contradicted the submitted request")


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


def _optional_string_list(value: Any, field_name: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"Rack AI field must be a list of strings: {field_name}")
    return [_string_value(item, f"{field_name} item") for item in value]


def _string_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value
