"""Adapter from existing ATHBA work units to the generic workspace port."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Mapping
from core.development.athba_workspace_routing import AthbaExecutionProfileResolver, AthbaProfileResolutionRequest
from core.development.work_unit import DevelopmentWorkUnit, WorkerExecutionProvenance
from core.execution.rack_ai_request import RepositoryBinding
from core.execution.work_unit_gateway import ExecutionPolicyEvidence, WorkUnitExecutionResult
from core.execution.workspace_execution_port import AiWorkspaceExecutionPort, WorkspaceExecutionRequest, WorkspaceExecutionResult, WorkspaceExecutionStatus

@dataclass(frozen=True)
class ProfiledWorkspaceGatewayDependencies:
    port: AiWorkspaceExecutionPort
    profiles: AthbaExecutionProfileResolver

class ProfiledWorkspaceExecutionGateway:
    """Preserves existing gateway callers while submitting generic workspace jobs."""
    def __init__(self, dependencies: ProfiledWorkspaceGatewayDependencies):
        self.port = dependencies.port
        self.profiles = dependencies.profiles

    async def execute(self, work_unit: DevelopmentWorkUnit, repository_binding: RepositoryBinding) -> WorkUnitExecutionResult:
        identity = work_unit.workspace_identity
        work_kind = work_unit.model_work_kind
        if identity is None or work_kind is None:
            raise ValueError("profiled workspace execution requires ATHBA model-work identity")
        profile = self.profiles.resolve(AthbaProfileResolutionRequest(work_kind, work_unit.timeout_seconds, work_unit.requires_large_context))
        if profile is None:
            raise ValueError("deterministic or reasoning-only work must not use the workspace port")
        request = WorkspaceExecutionRequest(identity, profile, repository_binding, tuple(work_unit.allowed_paths), work_unit.network, tuple(tuple(command) for command in work_unit.acceptance.commands), tuple(work_unit.acceptance.required_artifacts), work_unit.objective)
        return self._result_for(work_unit, self.port.submit_workspace_change(request))

    @staticmethod
    def _result_for(work_unit: DevelopmentWorkUnit, result: WorkspaceExecutionResult) -> WorkUnitExecutionResult:
        accepted = result.status == WorkspaceExecutionStatus.ACCEPTED and result.accepted_revision is not None
        return WorkUnitExecutionResult(
            work_unit.id, accepted, result.status.value,
            change_id=result.identity.submission_id,
            selected_worker_id=result.selected_worker_id,
            branch=result.branch,
            accepted_revision=result.accepted_revision,
            evidence_location=result.evidence_refs[0] if result.evidence_refs else None,
            worktree_path=result.worktree_ref,
            error=result.error,
            policy_evidence=ExecutionPolicyEvidence(list(work_unit.allowed_paths), list(result.changed_paths)),
            worker_provenance=_provenance_for(result),
        )

def _provenance_for(result: WorkspaceExecutionResult) -> WorkerExecutionProvenance | None:
    value = result.execution_provenance
    if value is None:
        return None
    return WorkerExecutionProvenance(
        worker_id=_required_provenance_string(value, "worker_id"),
        worker_role=_required_provenance_string(value, "worker_role"),
        worker_kind=_required_provenance_string(value, "worker_kind"),
        model_id=_required_provenance_string(value, "model_id"),
        provider_profile=_required_provenance_string(value, "provider_profile"),
        resource_id=_required_provenance_string(value, "resource_id"),
        backend=_required_provenance_string(value, "backend"),
        tool_profile=_optional_provenance_string(value, "tool_profile"),
    )


def _required_provenance_string(value: Mapping[str, object], name: str) -> str:
    item = _optional_provenance_string(value, name)
    if item is None:
        raise ValueError("workspace execution provenance is incomplete")
    return item


def _optional_provenance_string(value: Mapping[str, object], name: str) -> str | None:
    item = value.get(name)
    if item is None:
        return None
    if not isinstance(item, str) or not item.strip():
        raise ValueError("workspace execution provenance is malformed")
    return item
