"""Backend-neutral bounded workspace execution port."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from core.development.athba_workspace_routing import AthbaExecutionProfile, AthbaWorkspaceIdentity
from core.execution.rack_ai_request import RepositoryBinding

class WorkspaceExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    NO_CANDIDATE = "no_candidate"
    TIMEOUT = "timeout"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    DUPLICATE_SUBMISSION = "duplicate_submission"
    MALFORMED_RESULT = "malformed_result"
    SELECTION_EXECUTION_MISMATCH = "selection_execution_mismatch"
    CANCELLED = "cancelled"

@dataclass(frozen=True)
class WorkspaceExecutionRequest:
    """Generic request; ATHBA development-stage terms intentionally do not appear."""
    identity: AthbaWorkspaceIdentity
    profile: AthbaExecutionProfile
    repository: RepositoryBinding
    allowed_writable_paths: tuple[str, ...]
    network_policy: str
    acceptance_commands: tuple[tuple[str, ...], ...]
    required_artifacts: tuple[str, ...]
    objective: str
    # TODO(cleanup): The profiled gateway does not populate request evidence_refs and
    # the Rack AI v2 serializer does not transport them. Wire them through deliberately or remove the dead field.
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.allowed_writable_paths:
            raise ValueError("workspace request requires writable paths")
        if not self.acceptance_commands:
            raise ValueError("workspace request requires acceptance commands")
        if not isinstance(self.objective, str) or not self.objective.strip():
            raise ValueError("workspace objective must be non-empty")
        if not isinstance(self.network_policy, str) or not self.network_policy.strip():
            raise ValueError("workspace network policy must be non-empty")


@dataclass(frozen=True)
class WorkspaceExecutionResult:
    identity: AthbaWorkspaceIdentity
    status: WorkspaceExecutionStatus
    candidate_revision: str | None = None
    branch: str | None = None
    worktree_ref: str | None = None
    changed_paths: tuple[str, ...] = ()
    acceptance_verdict: str | None = None
    generic_failure: str | None = None
    selection_decision: dict[str, object] | None = None
    execution_provenance: dict[str, object] | None = None
    accepted_revision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    error: str | None = None
    selected_worker_id: str | None = None
    executed_worker_id: str | None = None

    def is_model_originated(self) -> bool:
        return self.status in {WorkspaceExecutionStatus.NO_CANDIDATE, WorkspaceExecutionStatus.TIMEOUT}

    def is_external_blocker(self) -> bool:
        return self.status in {WorkspaceExecutionStatus.BACKEND_UNAVAILABLE, WorkspaceExecutionStatus.CAPABILITY_UNAVAILABLE, WorkspaceExecutionStatus.TEMPORARILY_UNAVAILABLE, WorkspaceExecutionStatus.MALFORMED_RESULT, WorkspaceExecutionStatus.SELECTION_EXECUTION_MISMATCH}

class AiWorkspaceExecutionPort(Protocol):
    """Replaceable port for one generic bounded workspace-change operation."""
    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult: ...
    def get_result(self, submission_id: str) -> WorkspaceExecutionResult | None: ...
    def cancel(self, submission_id: str) -> bool: ...
