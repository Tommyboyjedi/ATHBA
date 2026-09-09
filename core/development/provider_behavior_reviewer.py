"""Provider-backed Senior Review for a completed strict-TDD behavior."""
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from core.development.behavior_completion import BehaviorReviewRequest, BehaviorReviewResult
from core.development.microcycle_domain import BehaviorReviewProtocolFailure
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest

MAX_REVIEW_RESPONSE_EVIDENCE_CHARACTERS = 4096
REVIEW_PURPOSE = "athba_senior_behavior_review"
REPAIR_PURPOSE = "athba_senior_behavior_review_json_repair"


@dataclass(frozen=True)
class SeniorBehaviorReviewResponseError(Exception):
    parse_error: str | None = None
    schema_error: str | None = None

    def detail(self) -> str:
        return self.schema_error or self.parse_error or "Senior behavior review could not be decoded"


class SeniorBehaviorReviewResponseDecoder:
    """Decodes one JSON object or one ordinary Markdown JSON fence."""

    def decode(self, text: str) -> BehaviorReviewResult:
        source = _normalise(text)
        try:
            payload = json.loads(source)
        except json.JSONDecodeError as error:
            raise SeniorBehaviorReviewResponseError(parse_error=str(error)) from error
        if not isinstance(payload, dict):
            raise SeniorBehaviorReviewResponseError(schema_error="Senior behavior review must be a JSON object")
        return _result(payload)


class ProviderSeniorBehaviorReviewer:
    """Requests one semantic verdict with at most one format-only repair."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway
        self.decoder = SeniorBehaviorReviewResponseDecoder()

    async def review(self, request: BehaviorReviewRequest) -> BehaviorReviewResult | BehaviorReviewProtocolFailure:
        initial = await self.gateway.reason(_request(request))
        try:
            return self.decoder.decode(initial.text)
        except SeniorBehaviorReviewResponseError as initial_error:
            repaired = await self.gateway.reason(_repair_request(request, initial.text, initial_error.detail()))
            try:
                return self.decoder.decode(repaired.text)
            except SeniorBehaviorReviewResponseError as repair_error:
                return _failure(initial.text, repaired.text, initial_error, repair_error)


def _request(request: BehaviorReviewRequest) -> ReasoningRequest:
    prompt = json.dumps({"instruction": "Act as ATHBA's Senior behavior reviewer. Return one JSON object.", "behavior_ticket": request.behavior_ticket, "canonical_test_identity": request.canonical_test_identity, "approved_scenario": request.approved_scenario, "production_diff": request.production_diff, "microcycle_evidence": list(request.microcycle_evidence), "regression_evidence": list(request.regression_evidence), "question": "Does the completed scenario and production change satisfy the requested observable behavior?", "required_output": {"verdict": "approved|repair_required|replan_required", "rationale": "brief evidence-based explanation", "findings": ["descriptive semantic defects only"], "evidence_refs": ["provided evidence identifiers only"]}, "rules": ["approve only when evidence supports the behavior", "repair_required needs findings", "approved has no repair findings", "replan_required explains why repair is insufficient", "do not invent evidence references"]}, sort_keys=True)
    return ReasoningRequest(REVIEW_PURPOSE, prompt, request.behavior_ticket)


def _repair_request(request: BehaviorReviewRequest, invalid: str, error: str) -> ReasoningRequest:
    prompt = json.dumps({"task": "Format-only repair of the previous Senior behavior-review response.", "invalid_response": invalid, "validation_error": error, "required_output": {"verdict": "approved|repair_required|replan_required", "rationale": "brief evidence-based explanation", "findings": ["descriptive semantic defects only"], "evidence_refs": ["provided evidence identifiers only"]}, "rules": ["return exactly one valid JSON object", "preserve the previous response's semantic decision and content as faithfully as possible", "do not perform a new behavior review or reconsider the decision", "do not add evidence, analysis, or findings not present in the previous response"]}, sort_keys=True)
    return ReasoningRequest(REPAIR_PURPOSE, prompt, request.behavior_ticket)


def _normalise(text: str) -> str:
    source = text.strip()
    fence = chr(96) * 3
    if not source.startswith(fence):
        return source
    lines = source.splitlines()
    if len(lines) < 3 or lines[-1].strip() != fence:
        return source
    if lines[0].strip()[len(fence):].strip() not in {"", "json"}:
        return source
    return "\n".join(lines[1:-1]).strip()


def _result(payload: dict[str, object]) -> BehaviorReviewResult:
    verdict = payload.get("verdict")
    rationale = payload.get("rationale")
    findings = _strings(payload.get("findings"), "findings")
    evidence_refs = _strings(payload.get("evidence_refs"), "evidence_refs")
    if not isinstance(verdict, str):
        raise SeniorBehaviorReviewResponseError(schema_error="Senior behavior review verdict must be text")
    if not isinstance(rationale, str) or not rationale.strip():
        raise SeniorBehaviorReviewResponseError(schema_error="Senior behavior review rationale must be non-empty text")
    try:
        return BehaviorReviewResult(verdict, rationale, evidence_refs, findings)
    except ValueError as error:
        raise SeniorBehaviorReviewResponseError(schema_error=str(error)) from error


def _strings(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise SeniorBehaviorReviewResponseError(schema_error=f"Senior behavior review {label} must be a list of non-empty strings")
    return tuple(value)


def _failure(first: str, repaired: str, initial: SeniorBehaviorReviewResponseError, repair: SeniorBehaviorReviewResponseError) -> BehaviorReviewProtocolFailure:
    return BehaviorReviewProtocolFailure(REVIEW_PURPOSE, 2, _digest(first), _digest(repaired), repair.parse_error or initial.parse_error, repair.schema_error or initial.schema_error, (f"reasoning:{REVIEW_PURPOSE}", f"reasoning:{REPAIR_PURPOSE}"))


def _digest(text: str) -> str:
    return sha256(text[:MAX_REVIEW_RESPONSE_EVIDENCE_CHARACTERS].encode("utf-8")).hexdigest()
