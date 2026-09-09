from dataclasses import replace

import pytest

from core.development.behavior_completion import (
    APPROVED,
    REPAIR_REQUIRED,
    BehaviorCompletionCommand,
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
        findings = ("semantic defect remains",) if self.verdict == REPAIR_REQUIRED else ()
        return BehaviorReviewResult(self.verdict, "reviewed", ("senior/evidence",), findings)


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
        await service.complete(BehaviorCompletionCommand(pending))
    complete = replace(pending, completion=ScenarioCompletion("scenario_complete", "green"))

    result = await service.complete(BehaviorCompletionCommand(complete, "production diff"))

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

    result = await service.complete(BehaviorCompletionCommand(complete))

    assert result.behavior_review.verdict == REPAIR_REQUIRED
    assert result.completion.status == "scenario_complete"
    assert starter.requests == []

@pytest.mark.asyncio
async def test_single_behavior_completion_needs_no_next_scenario_starter():
    reviewer = Reviewer(APPROVED)
    service = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer))
    complete = replace(initial_state(), completion=ScenarioCompletion("scenario_complete", "green"))

    result = await service.complete(BehaviorCompletionCommand(complete))

    assert result.completion.status == "behavior_complete"
    assert result.behavior_review.verdict == APPROVED
    assert result.behavior_review.next_behavior_ticket is None
    assert len(reviewer.requests) == 1

@pytest.mark.asyncio
async def test_protocol_failure_is_durable_and_restart_never_rereviews_or_starts_next_behavior():
    from core.development.microcycle_domain import BehaviorReviewProtocolFailure, MicrocycleState

    class ProtocolFailureReviewer:
        def __init__(self):
            self.calls = 0

        async def review(self, request):
            self.calls += 1
            return BehaviorReviewProtocolFailure(
                "athba_senior_behavior_review",
                2,
                "first-digest",
                "repair-digest",
                "not valid JSON",
                None,
                ("reasoning:athba_senior_behavior_review", "reasoning:athba_senior_behavior_review_json_repair"),
            )

    reviewer = ProtocolFailureReviewer()
    starter = Starter()
    state = replace(initial_state(), completion=ScenarioCompletion("scenario_complete", "canonical"))
    service = BehaviorCompletionService(BehaviorCompletionDependencies(reviewer, starter))

    failed = await service.complete(BehaviorCompletionCommand(state))
    reloaded = MicrocycleState.from_dict(failed.to_dict())
    resumed = await service.complete(BehaviorCompletionCommand(reloaded))

    assert failed.behavior_review.verdict == "protocol_failure"
    assert failed.behavior_review.attempts == 1
    assert failed.behavior_review.protocol_failure.response_attempts == 2
    assert failed.completion.completed_revision == "canonical"
    assert reloaded == failed
    assert resumed == failed
    assert reviewer.calls == 1
    assert starter.requests == []
