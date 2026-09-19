"""Assessment transitions keep the two tiny semantic lanes separate."""
from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
import re

from core.development.post_behavior_assessment import NamingDecision, RefactorDecision
from core.development.post_behavior_domain import (
    PostBehaviorCall, PostBehaviorOutcome, PostBehaviorPass, PostBehaviorPhase,
    PostBehaviorReason, PostBehaviorState, PostBehaviorStatus,
)
from core.development.post_behavior_journal import PostBehaviorJournal
from core.development.post_behavior_ports import PostBehaviorAssessmentPort

OBJECTIVE_TEXT_SIMILARITY = 0.85
OBJECTIVE_TOKEN_SIMILARITY = 0.8


class PostBehaviorAssessmentTransition:
    def __init__(self, journal: PostBehaviorJournal, assessors: PostBehaviorAssessmentPort):
        self.journal = journal
        self.assessors = assessors

    async def advance(self) -> PostBehaviorState:
        naming = self.journal.state.status == PostBehaviorStatus.NAMING_ASSESSMENT_PENDING
        phase = PostBehaviorPhase.NAMING if naming else PostBehaviorPhase.REFACTORING
        if self.journal.state.active_pass is None:
            self.journal.persist(replace(self.journal.state, active_pass=PostBehaviorPass(
                phase, len(self.journal.state.passes) + 1, self.journal.state.current_post_behavior_revision)))
        if self.journal.active().assessment is None:
            self.journal.mark(PostBehaviorCall.NAMING_ASSESSOR if naming else PostBehaviorCall.REFACTOR_ASSESSOR)
            assessment = await (self.assessors.assess_naming(self.journal.state) if naming
                                else self.assessors.assess_refactor(self.journal.state))
            self.journal.persist(replace(self.journal.state, active_pass=replace(
                self.journal.active(), assessment=assessment), pending_call=PostBehaviorCall.NONE))
        return self._naming() if naming else self._refactoring()

    def _naming(self) -> PostBehaviorState:
        assessment = self.journal.active().assessment
        assert assessment is not None and isinstance(assessment.decision, NamingDecision)
        if assessment.decision.rename is None:
            return self._stop(PostBehaviorOutcome.NO_CHANGE, PostBehaviorReason.NAMING_NO_CHANGE)
        for prior in self.journal.state.passes:
            if (prior.phase == PostBehaviorPhase.NAMING and prior.assessment is not None
                    and prior.assessment.decision == assessment.decision):
                return self.journal.reject(PostBehaviorReason.REPEATED_RENAME, "same exact rename already attempted in this lifecycle")
        return self.journal.persist(replace(self.journal.state, status=PostBehaviorStatus.NAMING_RENAME_PENDING))

    def _refactoring(self) -> PostBehaviorState:
        assessment = self.journal.active().assessment
        assert assessment is not None and isinstance(assessment.decision, RefactorDecision)
        opportunity = assessment.decision.opportunity
        if opportunity is None:
            return self._stop(PostBehaviorOutcome.NO_CHANGE, PostBehaviorReason.REFACTOR_NO_CHANGE)
        if self.journal.state.refactor_promoted_passes >= self.journal.state.policy.max_promoted_refactor_passes:
            return self._stop(PostBehaviorOutcome.BOUNDED_STOP, PostBehaviorReason.REFACTOR_LIMIT_REACHED)
        if repeated_objective(self.journal.state, opportunity.objective):
            return self._stop(PostBehaviorOutcome.BOUNDED_STOP, PostBehaviorReason.REPEATED_REFACTOR_OBJECTIVE)
        return self.journal.persist(replace(self.journal.state, status=PostBehaviorStatus.REFACTOR_CHANGE_PENDING))

    def _stop(self, outcome: PostBehaviorOutcome, reason: PostBehaviorReason) -> PostBehaviorState:
        active = replace(self.journal.active(), outcome=outcome, stop_reason=reason)
        status = (PostBehaviorStatus.NAMING_COMPLETE if active.phase == PostBehaviorPhase.NAMING
                  else PostBehaviorStatus.REFACTOR_COMPLETE)
        return self.journal.persist(replace(self.journal.state, status=status, active_pass=None,
                                           passes=(*self.journal.state.passes, active), terminal_reason=reason))


def repeated_objective(state: PostBehaviorState, objective: str) -> bool:
    for prior in state.passes:
        if prior.phase != PostBehaviorPhase.REFACTORING or prior.assessment is None:
            continue
        decision = prior.assessment.decision
        if isinstance(decision, RefactorDecision) and decision.opportunity is not None:
            if substantially_identical(objective, decision.opportunity.objective):
                return True
    return False


def substantially_identical(left: str, right: str) -> bool:
    first = " ".join(re.findall(r"\w+", left.casefold()))
    second = " ".join(re.findall(r"\w+", right.casefold()))
    tokens_first, tokens_second = set(first.split()), set(second.split())
    union = tokens_first | tokens_second
    overlap = len(tokens_first & tokens_second) / len(union) if union else 1.0
    return (first == second or overlap >= OBJECTIVE_TOKEN_SIMILARITY
            or SequenceMatcher(None, first, second).ratio() >= OBJECTIVE_TEXT_SIMILARITY)
