"""Deterministic fake for ATHBA workspace-port tests."""
from __future__ import annotations
from dataclasses import dataclass, field
from core.execution.workspace_execution_port import WorkspaceExecutionRequest, WorkspaceExecutionResult, WorkspaceExecutionStatus

@dataclass(frozen=True)
class FakeWorkspaceOutcome:
    status: WorkspaceExecutionStatus
    accepted_revision: str | None = None
    error: str | None = None
    selected_worker_id: str | None = "selected"
    executed_worker_id: str | None = "selected"
    evidence_refs: tuple[str, ...] = ()

@dataclass
class DeterministicFakeWorkspacePort:
    """Returns scripted generic outcomes and replays a submission idempotently."""
    outcomes: list[FakeWorkspaceOutcome] = field(default_factory=list)
    submitted: list[WorkspaceExecutionRequest] = field(default_factory=list)
    _results: dict[str, WorkspaceExecutionResult] = field(default_factory=dict)

    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult:
        prior = self._results.get(request.identity.submission_id)
        if prior is not None:
            return prior
        outcome = self.outcomes.pop(0) if self.outcomes else FakeWorkspaceOutcome(WorkspaceExecutionStatus.NO_CANDIDATE)
        result = WorkspaceExecutionResult(
            identity=request.identity,
            status=outcome.status,
            accepted_revision=outcome.accepted_revision,
            evidence_refs=outcome.evidence_refs,
            error=outcome.error,
            selected_worker_id=outcome.selected_worker_id,
            executed_worker_id=outcome.executed_worker_id,
        )
        self.submitted.append(request)
        self._results[request.identity.submission_id] = result
        return result

    def get_result(self, submission_id: str) -> WorkspaceExecutionResult | None:
        return self._results.get(submission_id)

    def cancel(self, submission_id: str) -> bool:
        return self._results.pop(submission_id, None) is not None
