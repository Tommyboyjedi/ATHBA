"""Execution boundary between ATHBA and an external work-unit executor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.execution.rack_ai_contract import RepositoryBinding


@dataclass(frozen=True)
class ExecutionPolicyEvidence:
    """Executor-reported path policy evidence for one candidate attempt."""

    allowed_paths: list[str]
    changed_paths: list[str]


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


class WorkUnitExecutionGateway(Protocol):
    """Port implemented by Rack AI adapters and deterministic test fakes."""

    async def execute(self, work_unit: object, repository_binding: RepositoryBinding) -> WorkUnitExecutionResult:
        """Execute one ready bounded work unit and return structured evidence."""
        ...
