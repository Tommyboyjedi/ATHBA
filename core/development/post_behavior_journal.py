"""Small durable effects shared by the explicit transition handlers."""
from __future__ import annotations

from dataclasses import replace

from core.development.post_behavior_domain import (
    PostBehaviorCall, PostBehaviorOutcome, PostBehaviorPass, PostBehaviorReason,
    PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_store import PostBehaviorStateRepository
from core.development.reconciliation_progress import ChecklistItemProgress


class PostBehaviorJournal:
    def __init__(self, repository: PostBehaviorStateRepository, state: PostBehaviorState):
        self.repository = repository
        self.state = state

    def persist(self, state: PostBehaviorState) -> PostBehaviorState:
        updated = replace(state, generation=self.state.generation + 1)
        self.repository.save(updated)
        self.state = updated
        return updated

    def mark(self, call: PostBehaviorCall) -> None:
        self.persist(replace(self.state, pending_call=call))

    def active(self) -> PostBehaviorPass:
        if self.state.active_pass is None:
            raise ValueError("post-behavior transition requires a pending pass")
        return self.state.active_pass

    def checkpoint(self, progress: tuple[ChecklistItemProgress, ...]) -> None:
        self.persist(replace(self.state, active_pass=replace(
            self.active(), reconciliation_progress=progress)))

    def blocked(self, reason: PostBehaviorReason, diagnostic: str) -> PostBehaviorState:
        return self.persist(replace(
            self.state, status=PostBehaviorStatus.BLOCKED,
            terminal_reason=reason, diagnostic=diagnostic))

    def reject(self, reason: PostBehaviorReason, diagnostic: str) -> PostBehaviorState:
        rejected = replace(self.active(), outcome=PostBehaviorOutcome.REJECTED, stop_reason=reason)
        return self.persist(replace(
            self.state, active_pass=None, passes=(*self.state.passes, rejected),
            pending_call=PostBehaviorCall.NONE, status=PostBehaviorStatus.BLOCKED,
            terminal_reason=reason, diagnostic=diagnostic))
