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
            "instruction": "Act as ATHBA's Senior behavior reviewer. Return one JSON object.",
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
                "findings": ["descriptive semantic defects only"],
                "evidence_refs": ["provided evidence identifiers only"],
            },
            "rules": [
                "approve only when the canonical scenario, regression evidence, and production diff support the behavior",
                "repair_required needs at least one descriptive semantic finding, never replacement source code",
                "approved has no repair findings",
                "replan_required explains why implementation repair is insufficient",
                "do not invent evidence references",
            ],
        },
        sort_keys=True,
    )
    return ReasoningRequest("athba_senior_behavior_review", prompt, request.behavior_ticket)


def _result_from_text(text: str) -> BehaviorReviewResult:
    payload = _json_object(text)
    evidence = payload.get("evidence_refs", [])
    findings = payload.get("findings", [])
    if not isinstance(evidence, list) or not isinstance(findings, list):
        raise ValueError("Senior behavior review findings and evidence refs must be lists")
    return BehaviorReviewResult(
        verdict=str(payload.get("verdict", "")),
        rationale=str(payload.get("rationale", "")),
        findings=tuple(str(item) for item in findings),
        evidence_refs=tuple(str(item) for item in evidence),
    )


def _json_object(text: str) -> dict[str, object]:
    source = text.strip()
    fence = chr(96) * 3
    if source.startswith(fence) and source.endswith(fence):
        source = source.split("\n", 1)[1].rsplit("\n", 1)[0].strip()
    try:
        payload = json.loads(source)
    except json.JSONDecodeError as error:
        raise ValueError("Senior behavior review response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("Senior behavior review response must be a JSON object")
    return payload
