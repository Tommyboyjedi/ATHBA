"""One-behavior, provider-neutral technical binding reconciliation."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256

from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult


TECHNICAL_BINDING_RESOLUTION_PURPOSE = "athba_technical_binding_resolution"
TECHNICAL_BINDING_FORMAT_REPAIR_PURPOSE = "athba_technical_binding_resolution_json_repair"
MAX_FORMAT_REPAIRS = 1


class TechnicalBindingResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    NO_BINDING_REQUIRED = "no_binding_required"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    PROTOCOL_FAILURE = "protocol_failure"


class TechnicalBindingRole(str, Enum):
    SUBJECT = "subject"
    ACTION = "action"
    OBSERVATION = "observation"
    STATE = "state"
    ERROR = "error"
    OTHER = "other"


@dataclass(frozen=True)
class TechnicalBindingBehavior:
    ref: str
    summary: str
    observable_outcome: str
    source_refs: tuple[str, ...] = ()
    source_clauses: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.ref, "behavior ref")
        _nonempty(self.summary, "behavior summary")
        _nonempty(self.observable_outcome, "behavior observable outcome")
        _unique_strings(self.source_refs, "behavior source refs")
        _unique_clause_refs(self.source_clauses)


@dataclass(frozen=True)
class TechnicalCandidate:
    technical_ref: str
    kind: str
    qualified_identifier: str
    origin: str
    repository_evidence: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, label in (
            (self.technical_ref, "technical ref"),
            (self.kind, "technical candidate kind"),
            (self.qualified_identifier, "technical candidate identifier"),
            (self.origin, "technical candidate origin"),
        ):
            _nonempty(value, label)
        _unique_strings(self.evidence_refs, "technical candidate evidence refs")


@dataclass(frozen=True)
class TechnicalBindingComponentContext:
    component_name: str
    source_excerpts: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _nonempty(self.component_name, "component name")
        _unique_clause_refs(self.source_excerpts)


@dataclass(frozen=True)
class InheritedTechnicalBindingConstraint:
    technical_ref: str
    role: TechnicalBindingRole | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        _nonempty(self.technical_ref, "inherited technical ref")


@dataclass(frozen=True)
class TechnicalBindingResolutionRequest:
    """Exactly one behavior and a bounded supplied technical catalogue."""

    behavior: TechnicalBindingBehavior
    technical_candidates: tuple[TechnicalCandidate, ...]
    component_context: TechnicalBindingComponentContext | None = None
    inherited_constraints: tuple[InheritedTechnicalBindingConstraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.technical_candidates:
            raise ValueError("technical binding resolution requires technical candidates")
        refs = tuple(candidate.technical_ref for candidate in self.technical_candidates)
        _unique_strings(refs, "technical candidate refs")
        candidate_refs = set(refs)
        for constraint in self.inherited_constraints:
            if constraint.technical_ref not in candidate_refs:
                raise ValueError("inherited technical constraint must reference a supplied candidate")

    @property
    def supplied_evidence_refs(self) -> frozenset[str]:
        refs = set(self.behavior.source_refs)
        refs.update(ref for ref, _ in self.behavior.source_clauses)
        for candidate in self.technical_candidates:
            refs.update(candidate.evidence_refs)
        if self.component_context:
            refs.update(ref for ref, _ in self.component_context.source_excerpts)
        return frozenset(refs)


@dataclass(frozen=True)
class TechnicalBinding:
    technical_ref: str
    role: TechnicalBindingRole


@dataclass(frozen=True)
class TechnicalBindingResolution:
    status: TechnicalBindingResolutionStatus
    behavior_ref: str
    bindings: tuple[TechnicalBinding, ...]
    rationale: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class TechnicalBindingResolutionTrace:
    resolution: TechnicalBindingResolution
    semantic_request: ReasoningRequest
    semantic_response: ReasoningResult | None
    repair_request: ReasoningRequest | None = None
    repair_response: ReasoningResult | None = None
    validation_error: str | None = None

    @property
    def format_repair_count(self) -> int:
        return int(self.repair_request is not None)

    @property
    def response_attempts(self) -> int:
        return int(self.semantic_response is not None) + int(self.repair_response is not None)


@dataclass(frozen=True)
class TechnicalBindingResponseError(Exception):
    detail: str


class TechnicalBindingResolutionDecoder:
    """Deterministically validates shape and supplied-reference boundaries only."""

    def decode(
        self,
        text: str,
        request: TechnicalBindingResolutionRequest,
    ) -> TechnicalBindingResolution:
        try:
            payload = json.loads(_normalise(text))
        except json.JSONDecodeError as error:
            raise TechnicalBindingResponseError(str(error)) from error
        if not isinstance(payload, dict):
            raise TechnicalBindingResponseError("technical binding resolution must be a JSON object")
        required = {"status", "behavior_ref", "bindings", "rationale", "evidence_refs"}
        if set(payload) != required:
            raise TechnicalBindingResponseError("technical binding resolution has unexpected or missing fields")
        try:
            status = TechnicalBindingResolutionStatus(payload["status"])
        except (TypeError, ValueError) as error:
            raise TechnicalBindingResponseError("technical binding resolution status is invalid") from error
        behavior_ref = payload["behavior_ref"]
        rationale = payload["rationale"]
        if not isinstance(behavior_ref, str) or behavior_ref != request.behavior.ref:
            raise TechnicalBindingResponseError("behavior_ref must equal the request behavior ref")
        if not isinstance(rationale, str) or not rationale.strip():
            raise TechnicalBindingResponseError("rationale must be non-empty text")
        evidence_refs = _string_tuple(payload["evidence_refs"], "evidence_refs")
        unknown_evidence = set(evidence_refs) - request.supplied_evidence_refs
        if unknown_evidence:
            raise TechnicalBindingResponseError("evidence_refs must be supplied evidence refs")
        bindings = self._bindings(payload["bindings"], request)
        _validate_status(status, bindings, evidence_refs, request)
        return TechnicalBindingResolution(status, behavior_ref, bindings, rationale.strip(), evidence_refs)

    def _bindings(
        self,
        value: object,
        request: TechnicalBindingResolutionRequest,
    ) -> tuple[TechnicalBinding, ...]:
        if not isinstance(value, list):
            raise TechnicalBindingResponseError("bindings must be a list")
        supplied = {candidate.technical_ref for candidate in request.technical_candidates}
        bindings: list[TechnicalBinding] = []
        for item in value:
            if not isinstance(item, dict) or set(item) != {"technical_ref", "role"}:
                raise TechnicalBindingResponseError("each binding must have technical_ref and role only")
            technical_ref = item["technical_ref"]
            if not isinstance(technical_ref, str) or technical_ref not in supplied:
                raise TechnicalBindingResponseError("binding technical_ref must be a supplied candidate")
            try:
                role = TechnicalBindingRole(item["role"])
            except (TypeError, ValueError) as error:
                raise TechnicalBindingResponseError("binding role is invalid") from error
            bindings.append(TechnicalBinding(technical_ref, role))
        refs = tuple(binding.technical_ref for binding in bindings)
        if len(refs) != len(set(refs)):
            raise TechnicalBindingResponseError("duplicate technical bindings are not allowed")
        return tuple(bindings)

def _validate_status(
    status: TechnicalBindingResolutionStatus,
    bindings: tuple[TechnicalBinding, ...],
    evidence_refs: tuple[str, ...],
    request: TechnicalBindingResolutionRequest,
) -> None:
    if status is TechnicalBindingResolutionStatus.RESOLVED:
        if not bindings:
            raise TechnicalBindingResponseError("resolved requires at least one binding")
        if not evidence_refs:
            raise TechnicalBindingResponseError("resolved requires supplied evidence refs")
    elif bindings:
        raise TechnicalBindingResponseError(f"{status.value} cannot contain authoritative bindings")
    if status is not TechnicalBindingResolutionStatus.RESOLVED:
        return
    roles_by_ref = {binding.technical_ref: binding.role for binding in bindings}
    for constraint in request.inherited_constraints:
        actual = roles_by_ref.get(constraint.technical_ref)
        if actual is None:
            raise TechnicalBindingResponseError("resolved must preserve inherited technical bindings")
        if constraint.role is not None and actual is not constraint.role:
            raise TechnicalBindingResponseError("resolved must preserve inherited technical binding role")


class TechnicalBindingResolver:
    """Uses one semantic request and at most one non-semantic format repair."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway
        self.decoder = TechnicalBindingResolutionDecoder()

    async def resolve(self, request: TechnicalBindingResolutionRequest) -> TechnicalBindingResolution:
        return (await self.resolve_with_trace(request)).resolution

    async def resolve_with_trace(
        self,
        request: TechnicalBindingResolutionRequest,
    ) -> TechnicalBindingResolutionTrace:
        semantic_request = _semantic_request(request)
        try:
            semantic_response = await self.gateway.reason(semantic_request)
        except Exception as error:  # Provider failures are terminal; no semantic retry is allowed.
            return _protocol_failure(request, semantic_request, None, None, None, str(error))
        try:
            resolution = self.decoder.decode(semantic_response.text, request)
            return TechnicalBindingResolutionTrace(resolution, semantic_request, semantic_response)
        except TechnicalBindingResponseError as error:
            initial_error_detail = error.detail
            repair_request = _format_repair_request(request, semantic_response.text, initial_error_detail)
        try:
            repair_response = await self.gateway.reason(repair_request)
        except Exception as repair_error:  # One repair was attempted; no further calls are allowed.
            return _protocol_failure(request, semantic_request, semantic_response, repair_request, None, str(repair_error))
        try:
            resolution = self.decoder.decode(repair_response.text, request)
            return TechnicalBindingResolutionTrace(
                resolution, semantic_request, semantic_response, repair_request, repair_response, initial_error_detail
            )
        except TechnicalBindingResponseError as repair_error:
            return _protocol_failure(
                request, semantic_request, semantic_response, repair_request, repair_response, repair_error.detail
            )


def _semantic_request(request: TechnicalBindingResolutionRequest) -> ReasoningRequest:
    prompt = json.dumps(
        {
            "instruction": "You are resolving technical bindings for ONE behavioral requirement. Return exactly one JSON object.",
            "behavior": {
                "ref": request.behavior.ref,
                "summary": request.behavior.summary,
                "observable_outcome": request.behavior.observable_outcome,
                "source_refs": list(request.behavior.source_refs),
                "source_clauses": [{"ref": ref, "text": text} for ref, text in request.behavior.source_clauses],
            },
            "technical_candidates": [
                {
                    "technical_ref": candidate.technical_ref,
                    "kind": candidate.kind,
                    "qualified_identifier": candidate.qualified_identifier,
                    "origin": candidate.origin,
                    "repository_evidence": candidate.repository_evidence,
                    "evidence_refs": list(candidate.evidence_refs),
                }
                for candidate in request.technical_candidates
            ],
            "component_context": _context(request.component_context),
            "inherited_binding_constraints": [
                {"technical_ref": item.technical_ref, "role": item.role.value if item.role else None, "rationale": item.rationale}
                for item in request.inherited_constraints
            ],
            "required_output": output_schema(),
            "rules": [
                "select only supplied technical candidates",
                "classify each selected candidate as subject, action, observation, state, error, or other",
                "do not invent technical identifiers",
                "do not redesign the behavior, write tests, write implementation, or invent architecture",
                "return no_binding_required when no supplied candidate is required",
                "return ambiguous when supplied candidates are genuinely indistinguishable",
                "return conflict when a required technical object is missing or conflicts with a mandatory inherited constraint",
                "preserve every inherited mandatory binding constraint",
                "use only supplied evidence_refs",
            ],
        },
        sort_keys=True,
    )
    return ReasoningRequest(TECHNICAL_BINDING_RESOLUTION_PURPOSE, prompt, request.behavior.ref)


def _format_repair_request(
    request: TechnicalBindingResolutionRequest,
    invalid_response: str,
    validation_error: str,
) -> ReasoningRequest:
    prompt = json.dumps(
        {
            "task": "Format-only repair of the previous technical-binding resolution response.",
            "behavior_ref": request.behavior.ref,
            "invalid_response": invalid_response,
            "validation_error": validation_error,
            "required_output": output_schema(),
            "rules": [
                "return exactly one valid JSON object",
                "preserve the previous response's semantic decision and content as faithfully as possible",
                "do not perform a new technical-binding resolution or reconsider the decision",
                "do not add technical identifiers, bindings, evidence, or analysis absent from the previous response",
            ],
        },
        sort_keys=True,
    )
    return ReasoningRequest(TECHNICAL_BINDING_FORMAT_REPAIR_PURPOSE, prompt, request.behavior.ref)


def output_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["status", "behavior_ref", "bindings", "rationale", "evidence_refs"],
        "properties": {
            "status": {"type": "string", "enum": [status.value for status in TechnicalBindingResolutionStatus]},
            "behavior_ref": {"type": "string"},
            "bindings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["technical_ref", "role"],
                    "properties": {
                        "technical_ref": {"type": "string"},
                        "role": {"type": "string", "enum": [role.value for role in TechnicalBindingRole]},
                    },
                },
            },
            "rationale": {"type": "string", "minLength": 1},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
    }


def output_schema_signature() -> str:
    return sha256(json.dumps(output_schema(), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _protocol_failure(
    request: TechnicalBindingResolutionRequest,
    semantic_request: ReasoningRequest,
    semantic_response: ReasoningResult | None,
    repair_request: ReasoningRequest | None,
    repair_response: ReasoningResult | None,
    error: str,
) -> TechnicalBindingResolutionTrace:
    resolution = TechnicalBindingResolution(
        TechnicalBindingResolutionStatus.PROTOCOL_FAILURE,
        request.behavior.ref,
        (),
        "Provider response could not be deterministically validated.",
        (),
    )
    return TechnicalBindingResolutionTrace(
        resolution, semantic_request, semantic_response, repair_request, repair_response, error
    )


def _context(context: TechnicalBindingComponentContext | None) -> dict[str, object] | None:
    if context is None:
        return None
    return {
        "component_name": context.component_name,
        "source_excerpts": [{"ref": ref, "text": text} for ref, text in context.source_excerpts],
    }


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


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise TechnicalBindingResponseError(f"{label} must be a list of non-empty strings")
    result = tuple(value)
    _unique_strings(result, label)
    return result


def _nonempty(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")


def _unique_strings(values: tuple[str, ...], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique non-empty strings")


def _unique_clause_refs(values: tuple[tuple[str, str], ...]) -> None:
    refs = tuple(ref for ref, text in values if isinstance(ref, str) and isinstance(text, str) and text.strip())
    if len(refs) != len(values) or len(refs) != len(set(refs)):
        raise ValueError("source excerpts must have unique refs and non-empty text")
