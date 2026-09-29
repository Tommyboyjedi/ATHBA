"""Explicit workspace-execution unavailability boundary."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.development.athba_workspace_routing import AthbaWorkspaceIdentity
from core.execution.workspace_execution_port import (
    WorkspaceExecutionRequest,
    WorkspaceExecutionResult,
    WorkspaceExecutionStatus,
)

UNSUPPORTED_WORKSPACE_EXECUTION_ERROR = (
    "rack_ai_workspace_execution_unavailable: "
    "RackAI workspace execution has no supported public result contract in this ATHBA phase"
)


@dataclass
class UnsupportedWorkspaceExecutionPort:
    """Fail closed where private RackAI workspace evidence was formerly required."""

    reason: str = UNSUPPORTED_WORKSPACE_EXECUTION_ERROR
    _results: dict[AthbaWorkspaceIdentity, WorkspaceExecutionResult] = field(default_factory=dict)

    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        result = WorkspaceExecutionResult(
            request.identity,
            WorkspaceExecutionStatus.CAPABILITY_UNAVAILABLE,
            error=self.reason,
        )
        self._results[request.identity] = result
        return result

    def get_result(self, identity: AthbaWorkspaceIdentity) -> WorkspaceExecutionResult | None:
        return self._results.get(identity)

    def cancel(self, submission_id: str) -> bool:
        return False
