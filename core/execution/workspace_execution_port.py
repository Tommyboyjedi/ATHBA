"""Backend-neutral bounded workspace execution port."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from core.development.athba_workspace_routing import AthbaExecutionProfile, AthbaWorkspaceIdentity
from core.execution.rack_ai_request import RepositoryBinding

class WorkspaceExecutionStatus(str, Enum):
    ACCEPTED = "accepted"
    NO_CANDIDATE = "no_candidate"
    TIMEOUT = "timeout"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
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

    def to_wire(self) -> dict[str, object]:
        return {"contract_version": "athba-workspace-execution/v1", "source_system": "athba", "work_id": self.identity.work_id, "submission_id": self.identity.submission_id, "idempotency_key": self.identity.idempotency_key, "capabilities": sorted(item.value for item in self.profile.required_capabilities), "complexity": self.profile.complexity.value, "requires_large_context": self.profile.requires_large_context, "priority": self.profile.priority.value, "timeout_seconds": self.profile.timeout_seconds, "repository": self.repository.to_dict(), "allowed_writable_paths": list(self.allowed_writable_paths), "environment_resources": list(self.repository.environment_resources), "network_policy": self.network_policy, "acceptance_commands": [list(item) for item in self.acceptance_commands], "required_artifacts": list(self.required_artifacts), "objective": self.objective, "evidence_refs": list(self.evidence_refs)}

@dataclass(frozen=True)
class WorkspaceExecutionResult:
    identity: AthbaWorkspaceIdentity
    status: WorkspaceExecutionStatus
    accepted_revision: str | None = None
    evidence_refs: tuple[str, ...] = ()
    error: str | None = None
    selected_worker_id: str | None = None
    executed_worker_id: str | None = None

    def is_model_originated(self) -> bool:
        return self.status in {WorkspaceExecutionStatus.NO_CANDIDATE, WorkspaceExecutionStatus.TIMEOUT}

    def is_external_blocker(self) -> bool:
        return self.status in {WorkspaceExecutionStatus.BACKEND_UNAVAILABLE, WorkspaceExecutionStatus.CAPABILITY_UNAVAILABLE, WorkspaceExecutionStatus.MALFORMED_RESULT, WorkspaceExecutionStatus.SELECTION_EXECUTION_MISMATCH}

class AiWorkspaceExecutionPort(Protocol):
    """Replaceable port for one generic bounded workspace-change operation."""
    def submit_workspace_change(self, request: WorkspaceExecutionRequest) -> WorkspaceExecutionResult: ...
    def get_result(self, submission_id: str) -> WorkspaceExecutionResult | None: ...
    def cancel(self, submission_id: str) -> bool: ...
