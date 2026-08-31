"""Regression coverage for the provider-backed Senior behavior review adapter."""
from __future__ import annotations

import json

import pytest

from core.development.behavior_completion import BehaviorReviewRequest
from core.development.provider_behavior_reviewer import ProviderSeniorBehaviorReviewer
from core.execution.reasoning_gateway import ReasoningResult


class RecordingGateway:
    def __init__(self, response: str):
        self.response = response
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.response, "local-primary", "local-primary")


def review_request() -> BehaviorReviewRequest:
    return BehaviorReviewRequest(
        "counter-behavior",
        "def test_counter():\n    assert 1 == 1\n",
        "tests/test_counter.py::test_counter",
        "diff --git a/counter.py",
        ("valid_behavioral_red", "green"),
        ("pytest current passed", "pytest suite passed"),
    )


@pytest.mark.asyncio
async def test_provider_reviewer_maps_one_evidence_based_verdict():
    gateway = RecordingGateway(
        json.dumps(
            {
                "verdict": "approved",
                "rationale": "The canonical test and deterministic regression both pass.",
                "evidence_refs": ["pytest current passed", "pytest suite passed"],
            }
        )
    )

    result = await ProviderSeniorBehaviorReviewer(gateway).review(review_request())

    assert result.verdict == "approved"
    assert result.evidence_refs == ("pytest current passed", "pytest suite passed")
    assert gateway.requests[0].purpose == "athba_senior_behavior_review"
    assert "diff --git a/counter.py" in gateway.requests[0].prompt


@pytest.mark.asyncio
async def test_provider_reviewer_rejects_non_json_response():
    gateway = RecordingGateway("not json")

    with pytest.raises(ValueError, match="not valid JSON"):
        await ProviderSeniorBehaviorReviewer(gateway).review(review_request())