"""Execution boundary between ATHBA and an external work-unit executor."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Protocol
from core.development.work_unit import WorkerExecutionProvenance
from core.execution.rack_ai_contract import RepositoryBinding

@dataclass(frozen=True)
class ExecutionPolicyEvidence:
    """Executor-reported path policy evidence for one candidate attempt."""
    allowed_paths: list[str]
    changed_paths: list[str]

@dataclass(frozen=True)
class WorkerRoutingExpectation:
    """Fail-closed evidence requirement for one live worker invocation."""
    worker_id: str
    worker_role: str
    model_id: str
    provider_profile: str
    resource_id: str
    def verify(self, result: WorkUnitExecutionResult) -> None:
        provenance = result.worker_provenance
        if provenance is None:
            raise ValueError("model-routing proof requires worker provenance")
        actual = (provenance.worker_id, provenance.worker_role, provenance.model_id, provenance.provider_profile, provenance.resource_id)
        expected = (self.worker_id, self.worker_role, self.model_id, self.provider_profile, self.resource_id)
        if actual != expected:
            raise ValueError("model-routing proof worker provenance did not match")

@dataclass(frozen=True)
class WorkUnitExecutionResult:
    """Executor-neutral result returned to the ATHBA application layer."""
    work_unit_id: str
    accepted: bool
    status: str
    change_id: str | None = None
    selected_worker_id: str | None = None
    placement: dict[str, Any] | None = None
    branch: str | None = None
    accepted_revision: str | None = None
    evidence_location: str | None = None
    worktree_path: str | None = None
    error: str | None = None
    policy_evidence: ExecutionPolicyEvidence | None = None
    worker_provenance: WorkerExecutionProvenance | None = None

class WorkUnitExecutionGateway(Protocol):
    """Port implemented by Rack AI adapters and deterministic test fakes."""
    async def execute(self, work_unit: object, repository_binding: RepositoryBinding) -> WorkUnitExecutionResult:
        """Execute one ready bounded work unit and return structured evidence."""
        ...
