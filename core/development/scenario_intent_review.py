"""Typed bounded scenario-intent review and protocol evidence."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, cast
from hashlib import sha256

from core.development.microcycle_domain import ScenarioIntentResult
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest

MAX_INTENT_RESPONSE_EVIDENCE_CHARACTERS = 4096


class ScenarioIntentReviewStatus(str, Enum):
    APPROVED = "approved"
    SEMANTIC_REPAIR_REQUIRED = "semantic_repair_required"
    WRONG_BEHAVIOR = "wrong_behavior"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    PROTOCOL_FAILURE = "protocol_failure"


class ScenarioIntentReviewRequest(Protocol):
    @property
    def scenario_id(self) -> str: ...

    @property
    def behavior_ref(self) -> str: ...


@dataclass(frozen=True)
class ScenarioIntentProtocolFailure:
    purpose: str
    attempt_count: int
    first_response_digest: str | None
    repair_response_digest: str | None
    parse_error: str | None
    schema_error: str | None
    evidence_refs: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "purpose": self.purpose,
            "attempt_count": self.attempt_count,
            "first_response_digest": self.first_response_digest,
            "repair_response_digest": self.repair_response_digest,
            "parse_error": self.parse_error,
            "schema_error": self.schema_error,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ScenarioIntentProtocolFailure":
        return cls(
            str(value["purpose"]), int(str(value["attempt_count"])),
            _optional(value.get("first_response_digest")),
            _optional(value.get("repair_response_digest")),
            _optional(value.get("parse_error")), _optional(value.get("schema_error")),
            _string_tuple(value.get("evidence_refs", ())),
        )


@dataclass(frozen=True)
class ScenarioIntentReviewOutcome:
    status: ScenarioIntentReviewStatus
    result: ScenarioIntentResult | None
    protocol_failure: ScenarioIntentProtocolFailure | None
    response_attempts: int
    reasoning_evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioIntentResponseError(Exception):
    parse_error: str | None = None
    schema_error: str | None = None

    def detail(self) -> str:
        return self.schema_error or self.parse_error or "intent response could not be decoded"


class ScenarioIntentResponseDecoder:
    """Decodes one JSON object or exactly one ordinary Markdown JSON fence."""

    def decode(self, scenario_id: str, text: str) -> ScenarioIntentResult:
        source = _normalise_json_object(text)
        try:
            payload = json.loads(source)
        except json.JSONDecodeError as error:
            raise ScenarioIntentResponseError(parse_error=str(error)) from error
        if not isinstance(payload, dict):
            raise ScenarioIntentResponseError(schema_error="scenario intent review must be a JSON object")
        return _intent_result(scenario_id, payload)


def _normalise_json_object(text: str) -> str:
    source = text.strip()
    fence = chr(96) * 3
    if not source.startswith(fence):
        return source
    lines = source.splitlines()
    if len(lines) < 3 or lines[-1].strip() != fence:
        return source
    language = lines[0].strip()[len(fence):].strip()
    if language not in {"", "json"}:
        return source
    return "\n".join(lines[1:-1]).strip()


def _intent_result(scenario_id: str, payload: dict[str, object]) -> ScenarioIntentResult:
    disposition = payload.get("disposition")
    feedback = payload.get("feedback")
    evidence = payload.get("evidence_refs")
    allowed = {"approved", "repair_required", "wrong_behavior", "insufficient_evidence"}
    if disposition not in allowed:
        raise ScenarioIntentResponseError(schema_error="scenario intent disposition is unsupported")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ScenarioIntentResponseError(schema_error="scenario intent feedback must be non-empty text")
    if not isinstance(evidence, list) or any(not isinstance(item, str) or not item.strip() for item in evidence):
        raise ScenarioIntentResponseError(schema_error="scenario intent evidence_refs must be non-empty strings")
    return ScenarioIntentResult(scenario_id, disposition, feedback, tuple(evidence))


class ScenarioIntentReviewer:
    """Requests bounded independent intent evidence without affecting Tester state."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway
        self.decoder = ScenarioIntentResponseDecoder()

    async def review(self, request: ScenarioIntentReviewRequest) -> ScenarioIntentReviewOutcome:
        initial = await self.gateway.reason(_request(request, "athba_scenario_intent_review", _intent_prompt(request)))
        try:
            result = self.decoder.decode(request.scenario_id, initial.text)
            return _success(result, 1)
        except ScenarioIntentResponseError as initial_error:
            repaired = await self.gateway.reason(_request(request, "athba_scenario_intent_json_repair", _intent_repair_prompt(initial.text, initial_error.detail())))
            try:
                result = self.decoder.decode(request.scenario_id, repaired.text)
                return _success(result, 2)
            except ScenarioIntentResponseError as repair_error:
                return _failure(initial.text, repaired.text, initial_error, repair_error)


def _request(request: ScenarioIntentReviewRequest, purpose: str, prompt: str) -> ReasoningRequest:
    return ReasoningRequest(purpose, prompt, request.behavior_ref, False)


def _success(result: ScenarioIntentResult, attempts: int) -> ScenarioIntentReviewOutcome:
    status = {
        "approved": ScenarioIntentReviewStatus.APPROVED,
        "repair_required": ScenarioIntentReviewStatus.SEMANTIC_REPAIR_REQUIRED,
        "wrong_behavior": ScenarioIntentReviewStatus.WRONG_BEHAVIOR,
        "insufficient_evidence": ScenarioIntentReviewStatus.INSUFFICIENT_EVIDENCE,
    }[result.status]
    return ScenarioIntentReviewOutcome(status, result, None, attempts, _evidence_refs(attempts))


def _failure(first: str, repaired: str, initial: ScenarioIntentResponseError, repair: ScenarioIntentResponseError) -> ScenarioIntentReviewOutcome:
    failure = ScenarioIntentProtocolFailure(
        "athba_scenario_intent_review", 2, _digest(first), _digest(repaired),
        repair.parse_error or initial.parse_error, repair.schema_error or initial.schema_error,
        _evidence_refs(2),
    )
    return ScenarioIntentReviewOutcome(ScenarioIntentReviewStatus.PROTOCOL_FAILURE, None, failure, 2, failure.evidence_refs)


def _evidence_refs(attempts: int) -> tuple[str, ...]:
    values = ["reasoning:athba_scenario_intent_review"]
    if attempts == 2:
        values.append("reasoning:athba_scenario_intent_json_repair")
    return tuple(values)


def _digest(text: str) -> str:
    return sha256(text[:MAX_INTENT_RESPONSE_EVIDENCE_CHARACTERS].encode("utf-8")).hexdigest()


def _optional(value: object) -> str | None:
    return None if value is None else str(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, (list, tuple)) else ()


def _intent_prompt(request: ScenarioIntentReviewRequest) -> str:
    from core.development.scenario_drafting import _intent_prompt as prompt
    return prompt(cast(Any, request))


def _intent_repair_prompt(invalid: str, error: str) -> str:
    from core.development.scenario_drafting import _intent_repair_prompt as prompt
    return prompt(invalid, error)
