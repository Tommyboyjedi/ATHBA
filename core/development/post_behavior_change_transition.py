"""One durable bounded workspace change, followed by independent validation."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from core.development.post_behavior_domain import (
    PostBehaviorCall, PostBehaviorPhase, PostBehaviorReason, PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_journal import PostBehaviorJournal
from core.development.post_behavior_ports import PostBehaviorMutationPort
from core.development.workspace_attempt_policy import (
    WorkspaceAttemptPolicy, WorkspaceAttemptState, WorkspaceSubmissionRecord,
)


class PostBehaviorChangeTransition:
    def __init__(self, journal: PostBehaviorJournal, mutation: PostBehaviorMutationPort):
        self.journal = journal
        self.mutation = mutation

    async def advance(self) -> PostBehaviorState:
        active = self.journal.active()
        if active.assessment is None:
            raise ValueError("post-behavior mutation requires a persisted decision")
        if active.candidate is None:
            if active.submission_id is None:
                self.journal.persist(replace(self.journal.state, active_pass=replace(
                    active, submission_id=uuid4().hex)))
            self.journal.mark(PostBehaviorCall.MUTATION)
            execution_result = await self.mutation.execute_change(self.journal.state)
            self.journal.persist(replace(self.journal.state, active_pass=replace(
                self.journal.active(), candidate=execution_result), pending_call=PostBehaviorCall.NONE))
        active = self.journal.active()
        candidate = active.candidate
        assert candidate is not None
        if not candidate.success or candidate.revision == active.base_revision:
            self._record_failure()
            return self.journal.reject(PostBehaviorReason.CANDIDATE_REJECTED,
                                       candidate.diagnostic or "mutation did not produce a changed accepted candidate")
        status = (PostBehaviorStatus.NAMING_VALIDATION_PENDING if active.phase == PostBehaviorPhase.NAMING
                  else PostBehaviorStatus.REFACTOR_VALIDATION_PENDING)
        return self.journal.persist(replace(self.journal.state, status=status))

    def _record_failure(self) -> None:
        active = self.journal.active()
        assert active.candidate is not None and active.submission_id is not None
        attempt = self.journal.state.attempt_state or WorkspaceAttemptState(uuid4().hex)
        candidate = active.candidate
        if candidate.model_originated:
            attempt = WorkspaceAttemptPolicy().record_model_failure(attempt, WorkspaceSubmissionRecord(
                active.submission_id, True, candidate.revision, candidate.evidence_refs[0]))
        else:
            attempt = WorkspaceAttemptPolicy.record_external_blocker(attempt)
        self.journal.persist(replace(self.journal.state, attempt_state=attempt))
