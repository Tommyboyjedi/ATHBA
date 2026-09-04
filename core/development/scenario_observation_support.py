"""Bounded private selection of declared observation support for one scenario."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from typing import Any

from core.development.behavior_contract_surface import DeclaredProductSurface
from core.development.specification_domain import SourceRequirementClause
from core.development.scenario_intent_review import _normalise_json_object
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest

MAX_OBSERVATION_EVIDENCE_REFS = 16
MAX_OBSERVATION_RESPONSE_CHARACTERS = 4096


class ScenarioObservationSupportStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    SUPPORT_SELECTED = "support_selected"
    UNRESOLVABLE = "unresolvable"
    PROTOCOL_FAILURE = "protocol_failure"


@dataclass(frozen=True)
class ScenarioObservationRequirement:
    ref: str
    summary: str
    observable_outcome: str


@dataclass(frozen=True)
class ScenarioObservationContext:
    behavior_ref: str
    behavior_summary: str
    expected_result: str
    test_hint: str
    source_requirements: tuple[SourceRequirementClause, ...]
    declared_surface: DeclaredProductSurface
    requirements: tuple[ScenarioObservationRequirement, ...]

    def __post_init__(self) -> None:
        if not self.behavior_ref.strip() or not self.declared_surface.machine_usable:
            raise ValueError("observation context requires one behavior and declared surface")
        if any(not item.ref.strip() for item in self.requirements):
            raise ValueError("observation context requirement refs must be non-empty")


@dataclass(frozen=True)
class ScenarioObservationProtocolFailure:
    attempt_count: int
    first_response_digest: str | None
    repair_response_digest: str | None
    error: str

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_count": self.attempt_count,
            "first_response_digest": self.first_response_digest,
            "repair_response_digest": self.repair_response_digest,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioObservationProtocolFailure":
        return cls(
            int(value["attempt_count"]),
            _optional(value.get("first_response_digest")),
            _optional(value.get("repair_response_digest")),
            str(value["error"]),
        )


@dataclass(frozen=True)
class ScenarioObservationSupport:
    behavior_ref: str
    status: str
    selected_members: tuple[str, ...] = ()
    reasoning_evidence_refs: tuple[str, ...] = ()
    response_attempts: int = 0
    protocol_failure: ScenarioObservationProtocolFailure | None = None

    def __post_init__(self) -> None:
        if self.status not in {item.value for item in ScenarioObservationSupportStatus}:
            raise ValueError("unsupported observation support status")
        if len(self.reasoning_evidence_refs) > MAX_OBSERVATION_EVIDENCE_REFS:
            raise ValueError("observation evidence refs exceed the limit")
        if self.status == ScenarioObservationSupportStatus.SUPPORT_SELECTED.value and not self.selected_members:
            raise ValueError("selected observation support requires members")
        if self.status != ScenarioObservationSupportStatus.SUPPORT_SELECTED.value and self.selected_members:
            raise ValueError("only selected observation support may contain members")

    def to_dict(self) -> dict[str, object]:
        return {
            "behavior_ref": self.behavior_ref,
            "status": self.status,
            "selected_members": list(self.selected_members),
            "reasoning_evidence_refs": list(self.reasoning_evidence_refs),
            "response_attempts": self.response_attempts,
            "protocol_failure": None if self.protocol_failure is None else self.protocol_failure.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ScenarioObservationSupport":
        failure = value.get("protocol_failure")
        return cls(
            str(value["behavior_ref"]), str(value["status"]),
            tuple(str(item) for item in value.get("selected_members", ())),
            tuple(str(item) for item in value.get("reasoning_evidence_refs", ())),
            int(value.get("response_attempts", 0)),
            None if failure is None else ScenarioObservationProtocolFailure.from_dict(dict(failure)),
        )


@dataclass(frozen=True)
class _Resolution:
    status: str
    selected_members: tuple[str, ...]
    evidence_refs: tuple[str, ...]


class ScenarioObservationResolver:
    """One semantic response plus at most one format-only repair."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def resolve(self, context: ScenarioObservationContext) -> ScenarioObservationSupport:
        first = await self.gateway.reason(ReasoningRequest(
            "athba_scenario_observation_support", _prompt(context), context.behavior_ref, False
        ))
        try:
            return _support(context, _decode(first.text), 1)
        except ValueError as initial_error:
            repaired = await self.gateway.reason(ReasoningRequest(
                "athba_scenario_observation_support_json_repair",
                _repair_prompt(first.text, str(initial_error)), context.behavior_ref, False,
            ))
            try:
                return _support(context, _decode(repaired.text), 2)
            except ValueError as repair_error:
                return ScenarioObservationSupport(
                    context.behavior_ref, ScenarioObservationSupportStatus.PROTOCOL_FAILURE.value,
                    (), (), 2, ScenarioObservationProtocolFailure(
                        2, _digest(first.text), _digest(repaired.text), str(repair_error),
                    ),
                )


def _decode(text: str) -> _Resolution:
    try:
        payload = json.loads(_normalise_json_object(text))
    except json.JSONDecodeError as error:
        raise ValueError(f"observation resolver response is not JSON: {error.msg}") from error
    if not isinstance(payload, dict):
        raise ValueError("observation resolver response must be an object")
    status = payload.get("status")
    selected = payload.get("selected_members")
    evidence = payload.get("evidence_refs")
    if status not in {"not_required", "support_selected", "unresolvable"}:
        raise ValueError("observation resolver status is unsupported")
    if not isinstance(selected, list) or any(not isinstance(item, str) or not item.strip() for item in selected):
        raise ValueError("observation resolver selected_members must be string list")
    if not isinstance(evidence, list) or any(not isinstance(item, str) or not item.strip() for item in evidence):
        raise ValueError("observation resolver evidence_refs must be string list")
    return _Resolution(status, tuple(selected), tuple(evidence))


def _support(context: ScenarioObservationContext, resolution: _Resolution, attempts: int) -> ScenarioObservationSupport:
    refs = {item.ref for item in context.requirements}
    if any(ref not in refs for ref in resolution.evidence_refs):
        raise ValueError("observation resolver referenced an unknown requirement")
    if resolution.status == "support_selected":
        if not resolution.selected_members or any(not context.declared_surface.allows_canonical(item) for item in resolution.selected_members):
            raise ValueError("observation resolver selected a non-canonical declared member")
        if len(set(resolution.selected_members)) != len(resolution.selected_members):
            raise ValueError("observation resolver selected duplicate members")
    elif resolution.selected_members:
        raise ValueError("observation resolver selected members without support_selected")
    return ScenarioObservationSupport(context.behavior_ref, resolution.status, resolution.selected_members, (), attempts)


def _prompt(context: ScenarioObservationContext) -> str:
    return json.dumps({
        "role": "private ScenarioObservationResolver",
        "question": "Is declared observation support required to demonstrate only the active behavior? Select the smallest public declared member set, or no support.",
        "active_behavior": {
            "ref": context.behavior_ref,
            "summary": context.behavior_summary,
            "observable_outcome": context.expected_result,
            "test_hint": context.test_hint,
            "source_requirements": [item.to_dict() for item in context.source_requirements],
        },
        "declared_public_api": list(context.declared_surface.canonical_members),
        "bounded_requirement_outcomes": [
            {"ref": item.ref, "summary": item.summary, "observable_outcome": item.observable_outcome}
            for item in context.requirements
        ],
        "response_schema": {
            "status": "not_required | support_selected | unresolvable",
            "selected_members": ["exact declared public API string"],
            "evidence_refs": ["Behavior Contract requirement ref"],
        },
    }, sort_keys=True)


def _repair_prompt(invalid: str, error: str) -> str:
    return json.dumps({
        "task": "Return only one valid JSON object for the previous observation support decision; do not make a second semantic decision.",
        "validation_error": error,
        "invalid_response": invalid[:MAX_OBSERVATION_RESPONSE_CHARACTERS],
    }, sort_keys=True)


def _digest(value: str) -> str:
    return sha256(value[:MAX_OBSERVATION_RESPONSE_CHARACTERS].encode("utf-8")).hexdigest()


def _optional(value: object) -> str | None:
    return None if value is None else str(value)
