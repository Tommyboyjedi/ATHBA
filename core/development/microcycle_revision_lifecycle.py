"""Explicit Git revision lifecycle for strict-TDD microcycles."""

from __future__ import annotations

from dataclasses import replace

from core.development.microcycle_revision_git import (
    ZERO_OBJECT_ID,
    MicrocycleGitClient,
    RevisionAncestryRequest,
    RevisionDeleteRequest,
    RevisionResolveRequest,
    RevisionUpdateRequest,
)
from core.development.microcycle_revision_state import (
    MicrocycleRevisionState,
    RevisionBindingRequest,
    RevisionCompletionRequest,
    RevisionInitialisationRequest,
    RevisionLifecycleStatus,
    RevisionRecoveryRequest,
    RevisionTransitionKind,
    RevisionTransitionRequest,
    RevisionTransitionResult,
)
from core.development.microcycle_revision_store import MicrocycleRevisionRepository, managed_working_ref
from core.execution.rack_ai_request import RepositoryBinding


class RevisionStateValidator:
    """Checks persisted revision state against actual Git refs."""

    def __init__(self, git: MicrocycleGitClient):
        self.git = git

    def validate_active(self, state: MicrocycleRevisionState) -> None:
        if self.git.resolve(RevisionResolveRequest(state.canonical_ref)) != state.canonical_development_base:
            raise ValueError("canonical development base diverged outside ATHBA")
        _verify_descendant(self.git, state.canonical_development_base, state.working_revision)
        if self.git.resolve(RevisionResolveRequest(state.working_ref)) != state.working_revision:
            raise ValueError("managed working ref diverged from persisted revision state")


class RevisionStateInitialiser:
    """Creates one managed ref at a verified canonical base, then persists it."""

    def __init__(self, repository: MicrocycleRevisionRepository, git: MicrocycleGitClient):
        self.repository = repository
        self.git = git

    def initialise(self, request: RevisionInitialisationRequest) -> MicrocycleRevisionState:
        prior = self.repository.load(request.scenario_id)
        if prior is not None:
            if prior.status != RevisionLifecycleStatus.ACTIVE.value:
                raise ValueError("completed scenario cannot recreate an active working ref")
            RevisionStateValidator(self.git).validate_active(prior)
            return prior
        if self.git.resolve(RevisionResolveRequest(request.canonical_ref)) != request.canonical_development_base:
            raise ValueError("canonical ref does not match requested development base")
        working_ref = managed_working_ref(request.scenario_id)
        if self.git.resolve(RevisionResolveRequest(working_ref)) is not None:
            raise ValueError("managed working ref exists without persisted revision state")
        state = MicrocycleRevisionState(
            request.scenario_id, request.canonical_ref, request.canonical_development_base,
            working_ref, request.canonical_development_base, RevisionLifecycleStatus.ACTIVE.value,
            RevisionTransitionKind.INITIALISED.value, request.evidence_refs,
        )
        self.git.update(RevisionUpdateRequest(working_ref, state.working_revision, ZERO_OBJECT_ID))
        try:
            self.repository.save(state)
        except Exception:
            self.git.delete(RevisionDeleteRequest(working_ref, state.working_revision))
            raise
        return state


class WorkingRevisionAdvancer:
    """CAS-advances only the managed working ref for accepted candidates."""

    def __init__(self, repository: MicrocycleRevisionRepository, git: MicrocycleGitClient):
        self.repository = repository
        self.git = git

    def advance(self, request: RevisionTransitionRequest) -> RevisionTransitionResult:
        if request.transition == RevisionTransitionKind.REGRESSION_CLEAR.value:
            raise ValueError("regression-clear promotion requires the canonical promoter")
        prior = _expected_active_state(self.repository, request.expected_current_state)
        RevisionStateValidator(self.git).validate_active(prior)
        _verify_descendant(self.git, prior.working_revision, request.candidate_revision)
        result = replace(
            prior, working_revision=request.candidate_revision, last_transition=request.transition,
            last_evidence_refs=request.evidence_refs,
        )
        self.git.update(RevisionUpdateRequest(prior.working_ref, result.working_revision, prior.working_revision))
        try:
            self.repository.save(result)
        except Exception:
            self.git.update(RevisionUpdateRequest(prior.working_ref, prior.working_revision, result.working_revision))
            raise
        return RevisionTransitionResult(prior, result, "working_ref_advanced")


class CanonicalDevelopmentBasePromoter:
    """CAS-promotes only a regression-cleared working revision."""

    def __init__(self, repository: MicrocycleRevisionRepository, git: MicrocycleGitClient):
        self.repository = repository
        self.git = git

    def promote(self, request: RevisionTransitionRequest) -> RevisionTransitionResult:
        if request.transition != RevisionTransitionKind.REGRESSION_CLEAR.value:
            raise ValueError("canonical promotion requires regression-clear evidence")
        prior = _expected_active_state(self.repository, request.expected_current_state)
        RevisionStateValidator(self.git).validate_active(prior)
        if request.candidate_revision != prior.working_revision:
            raise ValueError("regression-clear candidate must equal the working revision")
        _verify_descendant(self.git, prior.canonical_development_base, request.candidate_revision)
        result = replace(
            prior, canonical_development_base=request.candidate_revision,
            last_transition=request.transition, last_evidence_refs=request.evidence_refs,
        )
        self.git.update(RevisionUpdateRequest(
            prior.canonical_ref, result.canonical_development_base, prior.canonical_development_base
        ))
        try:
            self.repository.save(result)
        except Exception:
            self.git.update(RevisionUpdateRequest(
                prior.canonical_ref, prior.canonical_development_base, result.canonical_development_base
            ))
            raise
        return RevisionTransitionResult(prior, result, "canonical_development_base_promoted")


class RevisionRecoveryService:
    """Restores a missing persisted working ref and rejects all other divergence."""

    def __init__(self, repository: MicrocycleRevisionRepository, git: MicrocycleGitClient):
        self.repository = repository
        self.git = git

    def recover(self, request: RevisionRecoveryRequest) -> MicrocycleRevisionState:
        state = self.repository.load(request.scenario_id)
        if state is None:
            raise ValueError("unknown microcycle revision state")
        if self.git.resolve(RevisionResolveRequest(state.canonical_ref)) != state.canonical_development_base:
            raise ValueError("canonical development base diverged outside ATHBA")
        if state.status == RevisionLifecycleStatus.BEHAVIOR_COMPLETE.value:
            self._clean_completed_ref(state)
            return state
        _verify_descendant(self.git, state.canonical_development_base, state.working_revision)
        actual = self.git.resolve(RevisionResolveRequest(state.working_ref))
        if actual is None:
            self.git.update(RevisionUpdateRequest(state.working_ref, state.working_revision, ZERO_OBJECT_ID))
        elif actual != state.working_revision:
            raise ValueError("managed working ref diverged from persisted revision state")
        return state

    def _clean_completed_ref(self, state: MicrocycleRevisionState) -> None:
        actual = self.git.resolve(RevisionResolveRequest(state.working_ref))
        if actual is None:
            return
        if actual != state.canonical_development_base:
            raise ValueError("completed scenario has an unexpected working ref")
        self.git.delete(RevisionDeleteRequest(state.working_ref, actual))


class RevisionCompletionService:
    """Deletes the managed ref once canonical and working revisions align."""

    def __init__(self, repository: MicrocycleRevisionRepository, git: MicrocycleGitClient):
        self.repository = repository
        self.git = git

    def complete(self, request: RevisionCompletionRequest) -> MicrocycleRevisionState:
        prior = _expected_active_state(self.repository, request.expected_current_state)
        RevisionStateValidator(self.git).validate_active(prior)
        if prior.working_revision != prior.canonical_development_base:
            raise ValueError("behavior completion requires canonical and working revisions to align")
        self.git.delete(RevisionDeleteRequest(prior.working_ref, prior.working_revision))
        result = replace(
            prior, status=RevisionLifecycleStatus.BEHAVIOR_COMPLETE.value,
            last_transition=RevisionTransitionKind.BEHAVIOR_COMPLETED.value,
            last_evidence_refs=request.evidence_refs,
        )
        try:
            self.repository.save(result)
        except Exception:
            self.git.update(RevisionUpdateRequest(prior.working_ref, prior.working_revision, ZERO_OBJECT_ID))
            raise
        return result


class RackAiRevisionBindingFactory:
    """Builds a locally validated Rack AI ref/SHA binding from persisted state."""

    def __init__(
        self,
        recovery: RevisionRecoveryService,
        git: MicrocycleGitClient,
    ):
        self.recovery = recovery
        self.git = git

    def build(self, request: RevisionBindingRequest) -> RepositoryBinding:
        state = self.recovery.recover(RevisionRecoveryRequest(request.scenario_id))
        if state.status != RevisionLifecycleStatus.ACTIVE.value:
            raise ValueError("completed scenario has no active Rack AI working ref")
        if self.git.resolve(RevisionResolveRequest(state.working_ref)) != state.working_revision:
            raise ValueError("Rack AI binding ref/SHA invariant is not satisfied")
        return RepositoryBinding(
            repository_id=request.repository_id, base_ref=state.working_ref,
            base_sha=state.working_revision, registered_root=request.registered_root,
            environment_resources=list(request.environment_resources),
        )


def _expected_active_state(
    repository: MicrocycleRevisionRepository, expected: MicrocycleRevisionState
) -> MicrocycleRevisionState:
    current = repository.load(expected.scenario_id)
    if current != expected:
        raise ValueError("microcycle revision state compare-and-swap failed")
    if current.status != RevisionLifecycleStatus.ACTIVE.value:
        raise ValueError("microcycle revision state is not active")
    return current


def _verify_descendant(git: MicrocycleGitClient, base: str, candidate: str) -> None:
    if not git.commit_exists(RevisionResolveRequest(candidate)):
        raise ValueError("candidate revision is unavailable")
    if not git.is_ancestor(RevisionAncestryRequest(base, candidate)):
        raise ValueError("revision transition must be fast-forward")