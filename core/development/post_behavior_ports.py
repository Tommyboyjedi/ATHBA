"""ATHBA-owned capability ports; model adapters construct their narrow DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from core.development.post_behavior_domain import (
    ChangeCandidate, PostBehaviorAssessment, PostBehaviorState, ValidationEvidence,
)
from core.development.reconciliation_progress import ChecklistItemProgress

ReconciliationCheckpoint = Callable[[tuple[ChecklistItemProgress, ...]], None]


class PostBehaviorAssessmentPort(Protocol):
    async def assess_naming(self, state: PostBehaviorState) -> PostBehaviorAssessment:
        ...

    async def assess_refactor(self, state: PostBehaviorState) -> PostBehaviorAssessment:
        ...


class PostBehaviorMutationPort(Protocol):
    async def execute_change(self, state: PostBehaviorState) -> ChangeCandidate:
        ...


class PostBehaviorValidationPort(Protocol):
    async def test_candidate(self, state: PostBehaviorState) -> ValidationEvidence:
        ...

    async def reconcile_candidate(
        self, state: PostBehaviorState, checkpoint: ReconciliationCheckpoint,
    ) -> ValidationEvidence:
        ...


class PostBehaviorPromotionPort(Protocol):
    async def promote_candidate(self, state: PostBehaviorState) -> tuple[str, ...]:
        """Idempotently CAS the accepted ref; recover an already-applied identical CAS."""
        ...


@dataclass(frozen=True)
class PostBehaviorPorts:
    assessors: PostBehaviorAssessmentPort
    mutation: PostBehaviorMutationPort
    validation: PostBehaviorValidationPort
    promotion: PostBehaviorPromotionPort
