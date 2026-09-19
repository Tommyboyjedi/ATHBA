"""Explicit PR30 transition dispatch; infrastructure adapters own external effects."""
from __future__ import annotations

from dataclasses import replace

from core.development.post_behavior_assessment_transition import PostBehaviorAssessmentTransition
from core.development.post_behavior_change_transition import PostBehaviorChangeTransition
from core.development.post_behavior_domain import (
    PostBehaviorCall, PostBehaviorEntry, PostBehaviorPolicy, PostBehaviorReason,
    PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_journal import PostBehaviorJournal
from core.development.post_behavior_ports import PostBehaviorPorts
from core.development.post_behavior_store import PostBehaviorStateRepository
from core.development.post_behavior_validation_transition import PostBehaviorValidationTransition
from core.development.reconciliation_progress import PendingReconciliationCall

RESTART_SAFE_CALLS = frozenset({PostBehaviorCall.NONE, PostBehaviorCall.TESTS, PostBehaviorCall.PROMOTION})


class PostBehaviorLifecycle:
    def __init__(self, repository: PostBehaviorStateRepository, ports: PostBehaviorPorts):
        self.repository = repository
        self.ports = ports

    def start(self, entry: PostBehaviorEntry, policy: PostBehaviorPolicy | None = None) -> PostBehaviorState:
        prior = self.repository.load(entry.delivery_id)
        requested_policy = policy or PostBehaviorPolicy()
        if prior is not None:
            if prior.entry != entry or prior.policy != requested_policy:
                raise ValueError("post-behavior restart authority, baseline or policy changed")
            return prior
        state = PostBehaviorState(entry, entry.behaviorally_accepted_revision, policy=requested_policy)
        self.repository.save(state)
        return state

    async def advance(self, delivery_id: str) -> PostBehaviorState:
        state = self.repository.load(delivery_id)
        if state is None:
            raise ValueError("post-behavior processing requires a persisted Gatekeeper-approved entry")
        if state.terminal:
            return state
        journal = PostBehaviorJournal(self.repository, state)
        if not restart_safe(state):
            return journal.blocked(PostBehaviorReason.INTERRUPTED_CALL,
                                   f"{state.pending_call.value} began without a durable result")
        try:
            return await PostBehaviorTransitionDispatch(journal, self.ports).advance()
        except Exception as error:
            if journal.state.pending_call == PostBehaviorCall.PROMOTION:
                raise
            return journal.blocked(PostBehaviorReason.HUMAN_INTERVENTION,
                                   f"{type(error).__name__}: {error}")

    async def run(self, delivery_id: str) -> PostBehaviorState:
        state = await self.advance(delivery_id)
        while not state.terminal:
            state = await self.advance(delivery_id)
        return state


class PostBehaviorTransitionDispatch:
    def __init__(self, journal: PostBehaviorJournal, ports: PostBehaviorPorts):
        self.journal = journal
        self.ports = ports

    async def advance(self) -> PostBehaviorState:
        status = self.journal.state.status
        if status in {PostBehaviorStatus.NAMING_ASSESSMENT_PENDING, PostBehaviorStatus.REFACTOR_ASSESSMENT_PENDING}:
            return await PostBehaviorAssessmentTransition(self.journal, self.ports.assessors).advance()
        if status in {PostBehaviorStatus.NAMING_RENAME_PENDING, PostBehaviorStatus.REFACTOR_CHANGE_PENDING}:
            return await PostBehaviorChangeTransition(self.journal, self.ports.mutation).advance()
        if status in {PostBehaviorStatus.NAMING_VALIDATION_PENDING, PostBehaviorStatus.REFACTOR_VALIDATION_PENDING}:
            return await PostBehaviorValidationTransition(self.journal, self.ports).advance()
        return self._milestone()

    def _milestone(self) -> PostBehaviorState:
        transitions = (
            (PostBehaviorStatus.BEHAVIOR_GATEKEEPER_ACCEPTED, PostBehaviorStatus.NAMING_ASSESSMENT_PENDING),
            (PostBehaviorStatus.NAMING_COMPLETE, PostBehaviorStatus.REFACTOR_ASSESSMENT_PENDING),
            (PostBehaviorStatus.REFACTOR_COMPLETE, PostBehaviorStatus.POST_BEHAVIOR_COMPLETE),
        )
        for current, following in transitions:
            if self.journal.state.status == current:
                return self.journal.persist(replace(self.journal.state, status=following))
        raise ValueError("post-behavior state has no legal transition")


def restart_safe(state: PostBehaviorState) -> bool:
    if state.pending_call in RESTART_SAFE_CALLS:
        return True
    if state.pending_call != PostBehaviorCall.GATEKEEPER or state.active_pass is None:
        return False
    progress = state.active_pass.reconciliation_progress
    return bool(progress) and all(item.pending_call == PendingReconciliationCall.NONE for item in progress)
