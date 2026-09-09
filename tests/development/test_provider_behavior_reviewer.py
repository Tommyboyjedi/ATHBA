"""Regression coverage for the provider-backed Senior behavior review adapter."""
from __future__ import annotations

import json
from hashlib import sha256

import pytest

from core.development.behavior_completion import BehaviorReviewRequest
from core.development.microcycle_domain import BehaviorReviewProtocolFailure
from core.development.provider_behavior_reviewer import (
    ProviderSeniorBehaviorReviewer,
    SeniorBehaviorReviewResponseDecoder,
    SeniorBehaviorReviewResponseError,
)
from core.execution.reasoning_gateway import ReasoningResult


class RecordingGateway:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "local-primary", "local-primary")


def review_request() -> BehaviorReviewRequest:
    return BehaviorReviewRequest(
        "example-behavior",
        "def test_example():\n    assert True\n",
        "tests/test_example.py::test_example",
        "diff --git a/example.py",
        ("valid_behavioral_red", "green"),
        ("pytest current passed", "pytest suite passed"),
    )


def approved_response() -> str:
    return json.dumps(
        {
            "verdict": "approved",
            "rationale": "The canonical test and deterministic regression both pass.",
            "findings": [],
            "evidence_refs": ["pytest current passed", "pytest suite passed"],
        }
    )


@pytest.mark.asyncio
async def test_valid_json_first_response_is_one_semantic_call():
    gateway = RecordingGateway([approved_response()])

    result = await ProviderSeniorBehaviorReviewer(gateway).review(review_request())

    assert result.verdict == "approved"
    assert len(gateway.requests) == 1
    assert gateway.requests[0].purpose == "athba_senior_behavior_review"


@pytest.mark.asyncio
async def test_supported_fenced_json_is_one_semantic_call():
    fence = chr(96) * 3
    gateway = RecordingGateway([f"{fence}json\n{approved_response()}\n{fence}"])

    result = await ProviderSeniorBehaviorReviewer(gateway).review(review_request())

    assert result.verdict == "approved"
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_malformed_then_valid_format_repair_has_two_responses_and_one_semantic_review():
    gateway = RecordingGateway(["not json", approved_response()])

    result = await ProviderSeniorBehaviorReviewer(gateway).review(review_request())

    assert result.verdict == "approved"
    assert [item.purpose for item in gateway.requests] == [
        "athba_senior_behavior_review",
        "athba_senior_behavior_review_json_repair",
    ]
    repair_prompt = gateway.requests[1].prompt
    assert "not json" in repair_prompt
    assert "Expecting value" in repair_prompt
    assert "do not perform a new behavior review" in repair_prompt
    assert "do not add evidence" in repair_prompt


@pytest.mark.asyncio
async def test_double_invalid_json_returns_bounded_typed_protocol_failure():
    gateway = RecordingGateway(["not json", "still not json"])

    result = await ProviderSeniorBehaviorReviewer(gateway).review(review_request())

    assert isinstance(result, BehaviorReviewProtocolFailure)
    assert result.response_attempts == 2
    assert result.first_response_digest == sha256(b"not json").hexdigest()
    assert result.repair_response_digest == sha256(b"still not json").hexdigest()
    assert result.parse_error is not None
    assert result.evidence_refs == (
        "reasoning:athba_senior_behavior_review",
        "reasoning:athba_senior_behavior_review_json_repair",
    )
    assert [item.purpose for item in gateway.requests] == [
        "athba_senior_behavior_review",
        "athba_senior_behavior_review_json_repair",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"verdict": "unsupported", "rationale": "x", "findings": [], "evidence_refs": []},
        {"verdict": "approved", "rationale": "", "findings": [], "evidence_refs": []},
        {"verdict": "approved", "rationale": "x", "findings": "bad", "evidence_refs": []},
        {"verdict": "approved", "rationale": "x", "findings": [], "evidence_refs": "bad"},
        {"verdict": "repair_required", "rationale": "x", "findings": [], "evidence_refs": []},
        {"verdict": "approved", "rationale": "x", "findings": ["bad"], "evidence_refs": []},
        {"verdict": "approved", "rationale": "x", "findings": [""], "evidence_refs": []},
        {"verdict": "approved", "rationale": "x", "findings": [], "evidence_refs": [""]},
    ],
)
def test_decoder_rejects_invalid_schema(payload):
    with pytest.raises(SeniorBehaviorReviewResponseError):
        SeniorBehaviorReviewResponseDecoder().decode(json.dumps(payload))
