"""A quiescent management seam between completed requirements, never inside a frontier."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from core.development.project_environment_port import PreparedProjectEnvironment
from core.development.project_environment_git import AncestryCheckRequest, CanonicalRefRequest
from core.development.strict_tdd_feature_domain import StrictTddFeatureState


@dataclass(frozen=True)
class FeatureCheckpointRequest:
    project_id: str
    state: StrictTddFeatureState


@dataclass(frozen=True)
class FeatureCheckpointResult:
    revision: str
    evidence_refs: tuple[str, ...]


class FeatureManagementCheckpoint(Protocol):
    async def synchronize(self, request: FeatureCheckpointRequest) -> FeatureCheckpointResult | None: ...

    def resume_available(self, request: FeatureCheckpointRequest) -> bool: ...


async def management_checkpoint(
    capability: FeatureManagementCheckpoint | None,
    authority: tuple[PreparedProjectEnvironment, StrictTddFeatureState],
) -> StrictTddFeatureState:
    environment, state = authority
    if capability is None or not state.completed_behaviors or state.current_scenario_id is not None:
        return state
    if state.working_ref or state.working_revision or state.pending_completed_behavior or state.final_reconciliation:
        return state
    result = await capability.synchronize(FeatureCheckpointRequest(state.project_id, state))
    if result is None or result.revision == state.canonical_development_base:
        return state
    project = environment.repo.load(state.project_id)
    if project is None or project.trusted_base_sha != result.revision or not result.evidence_refs:
        raise ValueError("management checkpoint lacks exact trusted validation authority")
    root = Path(project.repository_root)
    git = environment._git_client()
    branch_ref = f"refs/heads/{project.default_ref}"
    if state.canonical_ref != branch_ref:
        raise ValueError("management checkpoint authority differs from the delivery branch")
    canonical = git.canonical_revision(CanonicalRefRequest(root, branch_ref))
    if canonical != result.revision or not git.is_ancestor(AncestryCheckRequest(
        root, str(state.canonical_development_base), result.revision,
    )):
        raise ValueError("management checkpoint did not advance the trusted delivery branch")
    if git.run(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("management checkpoint left an unverified working tree")
    history = state.reconciliation_history
    if state.reconciliation_progress:
        history = (*history, {"revision": state.canonical_development_base,
            "results": list(state.final_reconciliation), "progress": list(state.reconciliation_progress)})
    return replace(state, canonical_development_base=result.revision,
        reconciliation_progress=(), reconciliation_history=history,
        evidence_refs=(*state.evidence_refs, *result.evidence_refs))


def management_resume_available(
    capability: FeatureManagementCheckpoint | None, state: StrictTddFeatureState | None,
) -> bool:
    if capability is None or state is None or not state.completed_behaviors:
        return False
    if (state.current_scenario_id or state.working_ref or state.working_revision
            or state.pending_completed_behavior or state.final_reconciliation):
        return False
    return capability.resume_available(FeatureCheckpointRequest(state.project_id, state))
