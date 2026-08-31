from dataclasses import replace

import pytest

from core.development.behavior_completion import (
    APPROVED,
    REPAIR_REQUIRED,
    BehaviorCompletionDependencies,
    BehaviorCompletionService,
    BehaviorReviewResult,
)
from core.development.microcycle_domain import ScenarioCompletion
from tests.development.test_strict_microcycle import initial_state


class Reviewer:
    def __init__(self, verdict):
        self.verdict = verdict
        self.requests = []

    async def review(self, request):
        self.requests.append(request)
        return BehaviorReviewResult(self.verdict, "reviewed", ("senior/evidence",))


class Starter:
    def __init__(self):
        self.requests = []

    async def start(self, request):
        self.requests.append(request)
        return "next-behavior-scenario"


@pytest.mark.asyncio
async def test_senior_review_runs_only_after_complete_scenario_then_starts_next_behavior():
    reviewer, starter = Reviewer(APPROVED), Starter()
    service = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer, starter))
    pending = initial_state()

    with pytest.raises(ValueError, match="complete scenario"):
        await service.complete(pending)
    complete = replace(pending, completion=ScenarioCompletion("scenario_complete", "green"))

    result = await service.complete(complete, "production diff")

    assert result.completion.status == "behavior_complete"
    assert result.behavior_review.verdict == APPROVED
    assert result.behavior_review.next_behavior_ticket == "next-behavior-scenario"
    assert len(reviewer.requests) == len(starter.requests) == 1
    assert reviewer.requests[0].approved_scenario == complete.model.complete_source


@pytest.mark.asyncio
async def test_review_repair_does_not_complete_or_start_next_behavior():
    reviewer, starter = Reviewer(REPAIR_REQUIRED), Starter()
    service = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer, starter))
    complete = replace(initial_state(), completion=ScenarioCompletion("scenario_complete", "green"))

    result = await service.complete(complete)

    assert result.behavior_review.verdict == REPAIR_REQUIRED
    assert result.completion.status == "scenario_complete"
    assert starter.requests == []
