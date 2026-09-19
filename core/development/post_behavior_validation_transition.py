"""Checkpoint tests, existing Gatekeeper reconciliation, and accepted promotion separately."""
from __future__ import annotations

from dataclasses import replace

from core.development.post_behavior_domain import (
    PostBehaviorCall, PostBehaviorOutcome, PostBehaviorPhase, PostBehaviorReason,
    PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_journal import PostBehaviorJournal
from core.development.post_behavior_ports import PostBehaviorPorts


class PostBehaviorValidationTransition:
    def __init__(self, journal: PostBehaviorJournal, ports: PostBehaviorPorts):
        self.journal = journal
        self.ports = ports

    async def advance(self) -> PostBehaviorState:
        active = self.journal.active()
        if active.candidate is None or not active.candidate.success:
            raise ValueError("post-behavior validation requires an execution candidate")
        if active.tests is None:
            return await self._tests()
        if not active.tests.passed:
            return self.journal.reject(PostBehaviorReason.TESTS_FAILED, active.tests.diagnostic)
        if active.gatekeeper is None:
            return await self._gatekeeper()
        if not active.gatekeeper.passed:
            return self.journal.reject(PostBehaviorReason.GATEKEEPER_FAILED, active.gatekeeper.diagnostic)
        return await self._promote()

    async def _tests(self) -> PostBehaviorState:
        self.journal.mark(PostBehaviorCall.TESTS)
        evidence = await self.ports.validation.test_candidate(self.journal.state)
        return self.journal.persist(replace(self.journal.state, active_pass=replace(
            self.journal.active(), tests=evidence), pending_call=PostBehaviorCall.NONE))

    async def _gatekeeper(self) -> PostBehaviorState:
        self.journal.mark(PostBehaviorCall.GATEKEEPER)
        evidence = await self.ports.validation.reconcile_candidate(self.journal.state, self.journal.checkpoint)
        return self.journal.persist(replace(self.journal.state, active_pass=replace(
            self.journal.active(), gatekeeper=evidence), pending_call=PostBehaviorCall.NONE))

    async def _promote(self) -> PostBehaviorState:
        self.journal.mark(PostBehaviorCall.PROMOTION)
        evidence = await self.ports.promotion.promote_candidate(self.journal.state)
        active = self.journal.active()
        assert active.candidate is not None and active.candidate.revision is not None
        completed = replace(active, outcome=PostBehaviorOutcome.PROMOTED, promotion_evidence=evidence)
        refactoring = active.phase == PostBehaviorPhase.REFACTORING
        status = (PostBehaviorStatus.REFACTOR_ASSESSMENT_PENDING if refactoring
                  else PostBehaviorStatus.NAMING_ASSESSMENT_PENDING)
        return self.journal.persist(replace(
            self.journal.state, active_pass=None, passes=(*self.journal.state.passes, completed),
            current_post_behavior_revision=active.candidate.revision, status=status,
            refactor_promoted_passes=self.journal.state.refactor_promoted_passes + int(refactoring),
            pending_call=PostBehaviorCall.NONE, terminal_reason=None))
