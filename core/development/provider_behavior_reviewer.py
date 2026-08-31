"""Provider-backed Senior Review for a completed strict-TDD behavior."""
from __future__ import annotations

import json

from core.development.behavior_completion import BehaviorReviewRequest, BehaviorReviewResult
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


class ProviderSeniorBehaviorReviewer:
    """Requests one independent behavior-level verdict from the reasoning boundary."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def review(self, request: BehaviorReviewRequest) -> BehaviorReviewResult:
        result = await self.gateway.reason(_request_for(request))
        return _result_from_text(result.text)


def _request_for(request: BehaviorReviewRequest) -> ReasoningRequest:
    prompt = json.dumps(
        {
            "instruction": "Act as ATHBA's Senior behavior reviewer. Return raw JSON only.",
            "behavior_ticket": request.behavior_ticket,
            "canonical_test_identity": request.canonical_test_identity,
            "approved_scenario": request.approved_scenario,
            "production_diff": request.production_diff,
            "microcycle_evidence": list(request.microcycle_evidence),
            "regression_evidence": list(request.regression_evidence),
            "question": "Does the completed scenario and production change satisfy the requested observable behavior?",
            "required_output": {
                "verdict": "approved|repair_required|replan_required",
                "rationale": "brief evidence-based explanation",
                "evidence_refs": ["provided evidence identifiers only"],
            },
            "rules": [
                "approve only when the canonical scenario, regression evidence, and production diff support the behavior",
                "request repair for an implementation or test gap",
                "request replan when the scenario cannot establish the requested behavior",
                "do not invent evidence references",
            ],
        },
        sort_keys=True,
    )
    return ReasoningRequest("athba_senior_behavior_review", prompt, request.behavior_ticket)


def _result_from_text(text: str) -> BehaviorReviewResult:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("Senior behavior review response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Senior behavior review response must be a JSON object")
    evidence = payload.get("evidence_refs", [])
    if not isinstance(evidence, list):
        raise ValueError("Senior behavior review evidence refs must be a list")
    return BehaviorReviewResult(
        verdict=str(payload.get("verdict", "")),
        rationale=str(payload.get("rationale", "")),
        evidence_refs=tuple(str(item) for item in evidence),
    )