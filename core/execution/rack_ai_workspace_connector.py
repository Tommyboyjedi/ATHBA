"""Rack AI anti-corruption connector for the generic workspace contract."""
from __future__ import annotations
from collections.abc import Sequence
from typing import Protocol
from core.development.athba_workspace_routing import AthbaOutboundPriority
from core.execution.workspace_execution_port import WorkspaceExecutionRequest, WorkspaceExecutionResult, WorkspaceExecutionStatus

class RackAiWorkspaceTransport(Protocol):
    def submit(self, payload: dict[str, object]) -> dict[str, object]: ...

class RackAiWorkspaceConnector:
    """Serializes only generic fields; final Rack AI schema adaptation remains local."""
    def __init__(self, transport: RackAiWorkspaceTransport):
        self.transport = transport
        self._results: dict[str, WorkspaceExecutionResult] = {}

    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        self._require_priority_ceiling(request)
        prior = self._results.get(request.identity.submission_id)
        if prior is not None:
            return prior
        result = self._translate(request, self.transport.submit(request.to_wire()))
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

    @staticmethod
    def _translate(request: WorkspaceExecutionRequest, payload: dict[str, object]) -> WorkspaceExecutionResult:
        if payload.get("submission_id") != request.identity.submission_id:
            return WorkspaceExecutionResult(request.identity, WorkspaceExecutionStatus.MALFORMED_RESULT, error="Rack AI submission identity mismatch")
        try:
            status = WorkspaceExecutionStatus(str(payload["status"]))
        except (KeyError, ValueError):
            return WorkspaceExecutionResult(request.identity, WorkspaceExecutionStatus.MALFORMED_RESULT, error="Rack AI status is malformed")
        selected = _text_or_none(payload.get("selected_worker_id"))
        executed = _text_or_none(payload.get("executed_worker_id"))
        if selected is not None and executed is not None and selected != executed:
            status = WorkspaceExecutionStatus.SELECTION_EXECUTION_MISMATCH
        return WorkspaceExecutionResult(request.identity, status, _text_or_none(payload.get("accepted_revision")), _evidence_refs(payload.get("evidence_refs", ())), _text_or_none(payload.get("error")), selected, executed)

def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Rack AI text fields must be non-empty strings")
    return value


def _evidence_refs(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("Rack AI evidence refs must be a sequence")
    return tuple(str(item) for item in value)
