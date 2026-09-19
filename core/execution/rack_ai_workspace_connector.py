"""Rack AI v2 anti-corruption connector for generic workspace execution."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from core.development.athba_workspace_routing import AthbaOutboundPriority
from core.execution.workspace_execution_port import (
    WorkspaceExecutionRequest,
    WorkspaceExecutionResult,
    WorkspaceExecutionStatus,
)

RACK_AI_WORK_UNIT_VERSION = "rack-ai/work-unit/v2"
ONE_MODEL_INVOCATION = 1


class RackAiWorkspaceTransport(Protocol):
    def submit(self, payload: dict[str, object]) -> dict[str, object]: ...


class RackAiWorkspaceConnector:
    """Adapts the ATHBA port to Rack AI without exporting ATHBA semantics."""

    def __init__(self, transport: RackAiWorkspaceTransport):
        self.transport = transport
        self._results: dict[str, WorkspaceExecutionResult] = {}
        self._serializer = RackAiV2WorkspaceSerializer()
        self._translator = RackAiV2ResultTranslator()

    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        self._require_priority_ceiling(request)
        prior = self._results.get(request.identity.submission_id)
        if prior is not None:
            return prior
        result = self._translator.translate(request, self.transport.submit(self._serializer.serialize(request)))
        self._results[request.identity.submission_id] = result
        return result

    def get_result(self, submission_id: str) -> WorkspaceExecutionResult | None:
        return self._results.get(submission_id)

    def cancel(self, submission_id: str) -> bool:
        return self._results.pop(submission_id, None) is not None

    @staticmethod
    def _require_priority_ceiling(request: WorkspaceExecutionRequest) -> None:
        if request.profile.priority not in {AthbaOutboundPriority.LOW, AthbaOutboundPriority.MEDIUM}:
            raise ValueError("ATHBA workspace priority must not exceed medium")


class RackAiV2WorkspaceSerializer:
    """Owns the exact Rack AI v2 document shape at the transport boundary."""

    def serialize(self, request: WorkspaceExecutionRequest) -> dict[str, object]:
        repository = {"id": request.repository.repository_id, "base_ref": request.repository.base_ref}
        if request.repository.base_sha is not None:
            repository["base_sha"] = request.repository.base_sha
        if request.repository.registered_root is not None:
            repository["root"] = request.repository.registered_root
        work_unit = {
            "id": request.identity.submission_id,
            "objective": request.objective,
            "allowed_paths": list(request.allowed_writable_paths),
            "acceptance": {
                "commands": [list(command) for command in request.acceptance_commands],
                "required_artifacts": list(request.required_artifacts),
            },
            "requirements": {
                "complexity": request.profile.complexity.value,
                "requires_large_context": request.profile.requires_large_context,
            },
            "limits": {
                "max_implementation_attempts": ONE_MODEL_INVOCATION,
                "timeout_seconds": request.profile.timeout_seconds,
                "network": request.network_policy,
            },
            "routing": {
                "source_system": "athba",
                "work_id": request.identity.work_id,
                "submission_id": request.identity.submission_id,
                "idempotency_key": request.identity.idempotency_key,
                "required_capabilities": list(_ordered_capabilities(request)),
                "priority": request.profile.priority.value,
            },
        }
        if request.repository.environment_resources:
            work_unit["environment_resources"] = list(request.repository.environment_resources)
        return {
            "version": RACK_AI_WORK_UNIT_VERSION,
            "workload": {"id": request.identity.work_id, "kind": "application-development"},
            "repository": repository,
            "work_unit": work_unit,
        }


class RackAiV2ResultTranslator:
    """Translates Rack AI terminal facts without deciding ATHBA progression."""

    def translate(self, request: WorkspaceExecutionRequest, payload: dict[str, object]) -> WorkspaceExecutionResult:
        try:
            return self._translate(request, payload)
        except (KeyError, TypeError, ValueError) as error:
            return WorkspaceExecutionResult(request.identity, WorkspaceExecutionStatus.MALFORMED_RESULT, error=str(error))

    def _translate(self, request: WorkspaceExecutionRequest, payload: Mapping[str, object]) -> WorkspaceExecutionResult:
        selection = _mapping_or_none(payload.get("selection_decision"), "selection decision")
        provenance = _mapping_or_none(payload.get("worker_provenance"), "execution provenance")
        submission_id = _optional_text(payload.get("submission_id")) or _optional_text(_field(selection, "submission_id"))
        if submission_id != request.identity.submission_id:
            raise ValueError("Rack AI submission identity mismatch")
        status = _status_for(payload)
        selected = _optional_text(_field(selection, "selected_worker_id")) or _optional_text(payload.get("selected_worker_id"))
        executed = _optional_text(_field(provenance, "worker_id")) or _optional_text(payload.get("executed_worker_id"))
        if selection is not None and provenance is not None and selected is not None and executed is not None and selected != executed:
            status = WorkspaceExecutionStatus.SELECTION_EXECUTION_MISMATCH
        verdict = _optional_text(payload.get("acceptance_verdict"))
        candidate = _optional_text(payload.get("candidate_revision")) or _optional_text(payload.get("accepted_revision")) or _optional_text(payload.get("head_sha"))
        packet = _optional_text(payload.get("packet_path"))
        evidence_refs = _evidence_refs(payload.get("evidence_refs", ()))
        if packet is not None and packet not in evidence_refs:
            evidence_refs = (*evidence_refs, packet)
        failure = _optional_text(payload.get("generic_failure")) or _optional_text(payload.get("last_error")) or _optional_text(payload.get("error"))
        return WorkspaceExecutionResult(
            identity=request.identity,
            status=status,
            accepted_revision=candidate if status == WorkspaceExecutionStatus.ACCEPTED else None,
            candidate_revision=candidate,
            branch=_optional_text(payload.get("branch")),
            worktree_ref=_optional_text(payload.get("worktree_path")) or _optional_text(payload.get("worktree_ref")),
            changed_paths=_text_tuple(payload.get("changed_paths", ())),
            acceptance_verdict=verdict,
            generic_failure=failure,
            selection_decision=selection,
            execution_provenance=provenance,
            evidence_refs=evidence_refs,
            error=failure,
            selected_worker_id=selected,
            executed_worker_id=executed,
        )


def _status_for(payload: Mapping[str, object]) -> WorkspaceExecutionStatus:
    raw_status = _optional_text(payload.get("status"))
    verdict = _optional_text(payload.get("acceptance_verdict"))
    if raw_status in {"accepted", "checks_passed"} and verdict in {None, "approved"}:
        return WorkspaceExecutionStatus.ACCEPTED
    if raw_status in {"rejected", "checks_failed", "failed"}:
        return WorkspaceExecutionStatus.REJECTED
    if raw_status is None:
        raise ValueError("Rack AI status is malformed")
    return WorkspaceExecutionStatus(raw_status)


def _mapping_or_none(value: object, label: str) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"Rack AI {label} must be an object")
    return {str(key): item for key, item in value.items()}


def _field(value: Mapping[str, object] | None, name: str) -> object:
    return None if value is None else value.get(name)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Rack AI text fields must be non-empty strings")
    return value


def _evidence_refs(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("Rack AI evidence refs must be a sequence")
    return _text_tuple(value)


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("Rack AI text collections must be sequences")
    return tuple(text for item in value if (text := _optional_text(item)) is not None)


def _ordered_capabilities(request: WorkspaceExecutionRequest) -> tuple:
    order = ("reasoning", "coding", "visual", "audio")
    requested = {item.value for item in request.profile.required_capabilities}
    return tuple(item for item in order if item in requested)
