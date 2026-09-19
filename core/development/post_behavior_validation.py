"""Exact write authority followed by complete accepted-suite execution."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from core.development.deterministic_regression import (
    RuntimeCommandRequest, SubprocessProjectRuntimeExecutor, FULL_SUITE_TARGET,
)
from core.development.post_behavior_assessment import NamingDecision
from core.development.post_behavior_authority import (
    PythonPostBehaviorAuthority, RenameAuthorityRequest, RefactorAuthorityRequest,
)
from core.development.post_behavior_domain import PostBehaviorEntry, PostBehaviorOutcome, PostBehaviorPass, PostBehaviorState, ValidationEvidence
from core.development.post_behavior_entry import AcceptedBehavioralDelivery
from core.development.post_behavior_evidence import PostBehaviorEvidenceStore
from core.development.post_behavior_git import PostBehaviorGit
from core.development.post_behavior_slice import (
    FocusedProductionSlice, PythonProductionSlice, ProductionSliceScope, SliceRequest,
)


@dataclass(frozen=True)
class PostBehaviorProductionRevision:
    entry: PostBehaviorEntry
    revision: str


@dataclass(frozen=True)
class PostBehaviorPassAuthority:
    entry: PostBehaviorEntry
    change: PostBehaviorPass


@dataclass(frozen=True)
class PostBehaviorSource:
    git: PostBehaviorGit

    def focused(self, state: PostBehaviorState) -> FocusedProductionSlice:
        return self.for_revision(PostBehaviorProductionRevision(state.entry, state.current_post_behavior_revision))

    def for_revision(self, request: PostBehaviorProductionRevision) -> FocusedProductionSlice:
        scope = ProductionSliceScope(request.entry.trusted_entry_revision,
                                     request.entry.behaviorally_accepted_revision, request.entry.production_paths)
        return PythonProductionSlice().derive(SliceRequest(
            self.git.snapshot(scope.entry_revision), self.git.snapshot(request.revision), scope))


@dataclass(frozen=True)
class PostBehaviorCandidateAuthority:
    source: PostBehaviorSource

    def verify(self, state: PostBehaviorState) -> None:
        if state.active_pass is None:
            raise ValueError("write authority requires a durable pending pass")
        self.verify_pass(PostBehaviorPassAuthority(state.entry, state.active_pass))

    def verify_pass(self, request: PostBehaviorPassAuthority) -> None:
        active = request.change
        if active.candidate is None or active.candidate.revision is None or active.assessment is None:
            raise ValueError("write authority requires the durable candidate and assessment")
        self.source.git.validate_candidate((active.base_revision, active.candidate.revision))
        production = self.source.for_revision(PostBehaviorProductionRevision(request.entry, active.base_revision))
        if active.assessment.slice_identity != production.identity:
            raise ValueError("assessed production slice identity has changed")
        trusted = self.source.git.snapshot(active.base_revision)
        candidate = self.source.git.snapshot(active.candidate.revision)
        decision = active.assessment.decision
        authority = PythonPostBehaviorAuthority()
        if isinstance(decision, NamingDecision):
            if decision.rename is None:
                raise ValueError("rename candidate lacks a mapping")
            result = authority.rename(RenameAuthorityRequest(trusted, candidate, production, decision.rename))
        else:
            if decision.opportunity is None:
                raise ValueError("refactor candidate lacks an objective")
            result = authority.refactor(RefactorAuthorityRequest(trusted, candidate, production))
        if not result.passed:
            raise ValueError(result.reason)

    def verify_history(self, state: PostBehaviorState) -> None:
        for item in state.passes:
            if item.outcome == PostBehaviorOutcome.PROMOTED:
                self.verify_pass(PostBehaviorPassAuthority(state.entry, item))
        self.verify(state)


@dataclass(frozen=True)
class PostBehaviorTestValidation:
    delivery: AcceptedBehavioralDelivery
    authority: PostBehaviorCandidateAuthority
    evidence: PostBehaviorEvidenceStore

    async def test_candidate(self, state: PostBehaviorState) -> ValidationEvidence:
        active = state.active_pass
        if active is None or active.candidate is None or active.candidate.revision is None:
            raise ValueError("candidate test validation has no exact revision")
        revision = active.candidate.revision
        try:
            self.authority.verify(state)
        except ValueError as error:
            ref = self.evidence.record("write_authority_rejected", {"revision": revision, "reason": str(error)})
            return ValidationEvidence(revision, False, (ref,), str(error))
        with self.authority.source.git.test_workspace(revision) as worktree:
            report = SubprocessProjectRuntimeExecutor().execute(RuntimeCommandRequest(
                worktree, FULL_SUITE_TARGET, tuple(self.delivery.project.runtime.test_command)))
            # Test execution must not alter tracked production or accepted test bodies.
            dirty = PostBehaviorGit(worktree).command(("status", "--porcelain", "--untracked-files=no"))
        ref = self.evidence.record("accepted_regression", {
            "revision": revision, "base_revision": active.base_revision,
            "submission_id": active.submission_id, "report": asdict(report)})
        passed = report.status == "passed" and not dirty
        return ValidationEvidence(revision, passed, (ref,), dirty or report.evidence_ref)
