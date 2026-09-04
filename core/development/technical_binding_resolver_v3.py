"""One-operation technical binding subset selection; earlier versions are immutable."""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256

from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult

SELECTION_PURPOSE = "athba_technical_binding_subset_selection_v3"
REPAIR_PURPOSE = "athba_technical_binding_subset_selection_v3_json_repair"


@dataclass(frozen=True)
class TechnicalBindingBehaviorV3:
    behavior_ref: str
    summary: str
    observable_outcome: str


@dataclass(frozen=True)
class TechnicalCandidateV3:
    technical_ref: str
    qualified_identifier: str


@dataclass(frozen=True)
class TechnicalBindingSelectionRequestV3:
    behavior: TechnicalBindingBehaviorV3
    candidates: tuple[TechnicalCandidateV3, ...]
    inherited_mandatory_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        candidate_refs = tuple(candidate.technical_ref for candidate in self.candidates)
        _unique_nonempty(candidate_refs, "candidate refs")
        _unique_nonempty(self.inherited_mandatory_refs, "inherited mandatory refs")
        if not set(self.inherited_mandatory_refs) <= set(candidate_refs):
            raise ValueError("inherited mandatory refs must be supplied candidates")


@dataclass(frozen=True)
class TechnicalBindingSelectionV3:
    behavior_ref: str
    selected_refs: tuple[str, ...]


@dataclass(frozen=True)
class OwnerExpansionV3:
    selected_refs: tuple[str, ...]
    owner_qualified_identifiers: tuple[str, ...]


@dataclass(frozen=True)
class SelectionTraceV3:
    request: ReasoningRequest
    response: ReasoningResult | None
    repair_request: ReasoningRequest | None
    repair_response: ReasoningResult | None
    validation_error: str | None

    @property
    def format_repair_count(self) -> int:
        return int(self.repair_request is not None)


@dataclass(frozen=True)
class TechnicalBindingResolutionV3:
    selection: TechnicalBindingSelectionV3 | None
    trace: SelectionTraceV3


class TechnicalBindingV3ResponseError(Exception):
    """A response cannot be accepted by deterministic validation."""


class TechnicalBindingResolverV3:
    """Uses one semantic selection call and at most one format-only repair."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def resolve(self, request: TechnicalBindingSelectionRequestV3) -> TechnicalBindingResolutionV3:
        semantic_request = ReasoningRequest(SELECTION_PURPOSE, selection_prompt(request), request.behavior.behavior_ref)
        try:
            response = await self.gateway.reason(semantic_request)
        except Exception as error:
            return TechnicalBindingResolutionV3(None, SelectionTraceV3(semantic_request, None, None, None, str(error)))
        try:
            selection = decode_selection(response.text, request)
        except TechnicalBindingV3ResponseError as error:
            repair_request = ReasoningRequest(REPAIR_PURPOSE, "Return the same selection in the required JSON shape.", request.behavior.behavior_ref)
            try:
                repair_response = await self.gateway.reason(repair_request)
            except Exception as repair_error:
                return TechnicalBindingResolutionV3(None, SelectionTraceV3(semantic_request, response, repair_request, None, str(repair_error)))
            try:
                selection = decode_selection(repair_response.text, request)
            except TechnicalBindingV3ResponseError as repair_error:
                return TechnicalBindingResolutionV3(None, SelectionTraceV3(semantic_request, response, repair_request, repair_response, str(repair_error)))
            return TechnicalBindingResolutionV3(selection, SelectionTraceV3(semantic_request, response, repair_request, repair_response, str(error)))
        return TechnicalBindingResolutionV3(selection, SelectionTraceV3(semantic_request, response, None, None, None))


def decode_selection(text: str, request: TechnicalBindingSelectionRequestV3) -> TechnicalBindingSelectionV3:
    try:
        payload = json.loads(_normalise_json_object(text))
    except json.JSONDecodeError as error:
        raise TechnicalBindingV3ResponseError(str(error)) from error
    if not isinstance(payload, dict) or set(payload) != {"behavior_ref", "selected_refs"}:
        raise TechnicalBindingV3ResponseError("response must contain only behavior_ref and selected_refs")
    behavior_ref = payload["behavior_ref"]
    selected_refs = payload["selected_refs"]
    if behavior_ref != request.behavior.behavior_ref:
        raise TechnicalBindingV3ResponseError("behavior_ref must exactly match the request")
    if not isinstance(selected_refs, list) or any(not isinstance(value, str) for value in selected_refs):
        raise TechnicalBindingV3ResponseError("selected_refs must be a list of text refs")
    refs = tuple(selected_refs)
    _unique_nonempty(refs, "selected refs")
    supplied = {candidate.technical_ref for candidate in request.candidates}
    if not set(refs) <= supplied:
        raise TechnicalBindingV3ResponseError("selected refs must be supplied candidates")
    if not set(request.inherited_mandatory_refs) <= set(refs):
        raise TechnicalBindingV3ResponseError("selected refs must include inherited mandatory refs")
    return TechnicalBindingSelectionV3(behavior_ref, refs)


def expand_owners(request: TechnicalBindingSelectionRequestV3, selection: TechnicalBindingSelectionV3) -> OwnerExpansionV3:
    if selection.behavior_ref != request.behavior.behavior_ref:
        raise ValueError("selection belongs to a different behavior")
    identifiers = {candidate.technical_ref: candidate.qualified_identifier for candidate in request.candidates}
    owners: list[str] = []
    for ref in selection.selected_refs:
        identifier = identifiers[ref]
        if "." not in identifier:
            continue
        owner = identifier.rsplit(".", 1)[0]
        if owner not in owners:
            owners.append(owner)
    return OwnerExpansionV3(selection.selected_refs, tuple(owners))


def selection_prompt(request: TechnicalBindingSelectionRequestV3) -> str:
    payload: dict[str, object] = {
        "instruction": "You are mapping ONE behavior to existing technical candidates. Return only candidate refs that genuinely belong to this behavior. Select only from the supplied refs. If none apply, return an empty selected_refs list. Do not invent anything.",
        "behavior": {
            "behavior_ref": request.behavior.behavior_ref,
            "summary": request.behavior.summary,
            "observable_outcome": request.behavior.observable_outcome,
        },
        "candidates": [
            {"technical_ref": candidate.technical_ref, "qualified_identifier": candidate.qualified_identifier}
            for candidate in request.candidates
        ],
        "required_json_schema": selection_schema(),
    }
    if request.inherited_mandatory_refs:
        payload["mandatory_refs"] = list(request.inherited_mandatory_refs)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def selection_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["behavior_ref", "selected_refs"],
        "properties": {
            "behavior_ref": {"type": "string"},
            "selected_refs": {"type": "array", "items": {"type": "string"}},
        },
    }


def selection_schema_signature() -> str:
    encoded = json.dumps(selection_schema(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _normalise_json_object(text: str) -> str:
    source = text.strip()
    fence = chr(96) * 3
    if source.startswith(fence):
        lines = source.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == fence and lines[0].strip()[3:].strip() in {"", "json"}:
            return "\n".join(lines[1:-1]).strip()
    return source


def _unique_nonempty(values: Sequence[str], label: str) -> None:
    if any(not value.strip() for value in values):
        raise TechnicalBindingV3ResponseError(f"{label} must be non-empty")
    if len(values) != len(set(values)):
        raise TechnicalBindingV3ResponseError(f"{label} must not contain duplicates")
