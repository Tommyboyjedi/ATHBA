"""Two-stage, one-behavior technical binding resolver; v1 remains immutable."""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256

from core.development.technical_binding_resolver import TechnicalBindingResolutionRequest
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult

STAGE1_PURPOSE = "athba_technical_binding_applicability_v2"
STAGE1_REPAIR_PURPOSE = "athba_technical_binding_applicability_v2_json_repair"
STAGE2_PURPOSE = "athba_technical_binding_selection_v2"
STAGE2_REPAIR_PURPOSE = "athba_technical_binding_selection_v2_json_repair"

class BindingApplicabilityStatus(str, Enum):
    BINDING_REQUIRED = "binding_required"
    NO_BINDING_REQUIRED = "no_binding_required"
    AMBIGUOUS = "ambiguous"
    CONFLICT = "conflict"
    PROTOCOL_FAILURE = "protocol_failure"

@dataclass(frozen=True)
class BindingApplicability:
    status: BindingApplicabilityStatus
    behavior_ref: str
    rationale: str
    evidence_refs: tuple[str, ...]

@dataclass(frozen=True)
class TechnicalBindingSelection:
    behavior_ref: str
    selected_technical_refs: tuple[str, ...]
    rationale: str
    evidence_refs: tuple[str, ...]

@dataclass(frozen=True)
class StageTrace:
    request: ReasoningRequest
    response: ReasoningResult | None
    repair_request: ReasoningRequest | None
    repair_response: ReasoningResult | None
    validation_error: str | None

    @property
    def repair_count(self) -> int:
        return int(self.repair_request is not None)

@dataclass(frozen=True)
class TechnicalBindingResolutionV2:
    stage1: BindingApplicability
    stage2: TechnicalBindingSelection | None
    stage1_trace: StageTrace
    stage2_trace: StageTrace | None

@dataclass(frozen=True)
class TechnicalBindingV2ResponseError(Exception):
    detail: str

@dataclass(frozen=True)
class _Stage:
    purpose: str
    repair_purpose: str
    decoder: Callable[..., object]

class TechnicalBindingResolverV2:
    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def resolve(self, request: TechnicalBindingResolutionRequest) -> TechnicalBindingResolutionV2:
        stage1, trace1 = await self._stage1(request)
        if stage1.status is not BindingApplicabilityStatus.BINDING_REQUIRED:
            return TechnicalBindingResolutionV2(stage1, None, trace1, None)
        stage2, trace2 = await self._stage2(request, stage1)
        return TechnicalBindingResolutionV2(stage1, stage2, trace1, trace2)

    async def _stage1(self, request: TechnicalBindingResolutionRequest) -> tuple[BindingApplicability, StageTrace]:
        prompt = _stage1_prompt(request)
        result, trace = await self._call_stage(request, prompt, _Stage(STAGE1_PURPOSE, STAGE1_REPAIR_PURPOSE, _decode_stage1))
        if result is None:
            result = BindingApplicability(
                BindingApplicabilityStatus.PROTOCOL_FAILURE,
                request.behavior.ref,
                "Provider response could not be deterministically validated.",
                (),
            )
        return result, trace

    async def _stage2(self, request: TechnicalBindingResolutionRequest, stage1: BindingApplicability) -> tuple[TechnicalBindingSelection | None, StageTrace]:
        prompt = _stage2_prompt(request, stage1)
        return await self._call_stage(request, prompt, _Stage(STAGE2_PURPOSE, STAGE2_REPAIR_PURPOSE, _decode_stage2))

    async def _call_stage(self, request, prompt, stage):
        semantic = ReasoningRequest(stage.purpose, prompt, request.behavior.ref)
        try:
            response = await self.gateway.reason(semantic)
        except Exception as error:
            return None, StageTrace(semantic, None, None, None, str(error))
        try:
            return stage.decoder(response.text, request), StageTrace(semantic, response, None, None, None)
        except TechnicalBindingV2ResponseError as error:
            validation_error = error.detail
            repair = ReasoningRequest(stage.repair_purpose, _repair_prompt(request, response.text, validation_error, stage.purpose), request.behavior.ref)
        try:
            repaired = await self.gateway.reason(repair)
        except Exception as error:
            return None, StageTrace(semantic, response, repair, None, str(error))
        try:
            return stage.decoder(repaired.text, request), StageTrace(semantic, response, repair, repaired, validation_error)
        except TechnicalBindingV2ResponseError as error:
            return None, StageTrace(semantic, response, repair, repaired, error.detail)

def _decode_stage1(text: str, request: TechnicalBindingResolutionRequest) -> BindingApplicability:
    payload = _object(text, {"status", "behavior_ref", "rationale", "evidence_refs"})
    try:
        status = BindingApplicabilityStatus(payload["status"])
    except (TypeError, ValueError) as error:
        raise TechnicalBindingV2ResponseError("stage 1 status is invalid") from error
    _behavior_and_rationale(payload, request)
    refs = _evidence(payload, request)
    return BindingApplicability(status, request.behavior.ref, payload["rationale"].strip(), refs)

def _decode_stage2(text: str, request: TechnicalBindingResolutionRequest) -> TechnicalBindingSelection:
    payload = _object(text, {"behavior_ref", "selected_technical_refs", "rationale", "evidence_refs"})
    _behavior_and_rationale(payload, request)
    selected = payload["selected_technical_refs"]
    if not isinstance(selected, list) or not selected or any(not isinstance(item, str) for item in selected):
        raise TechnicalBindingV2ResponseError("stage 2 selected_technical_refs must be a non-empty text list")
    refs = tuple(selected)
    if len(refs) != len(set(refs)):
        raise TechnicalBindingV2ResponseError("stage 2 selected_technical_refs must not contain duplicates")
    supplied = {candidate.technical_ref for candidate in request.technical_candidates}
    if not set(refs) <= supplied:
        raise TechnicalBindingV2ResponseError("stage 2 selected_technical_refs must be supplied candidates")
    mandatory = {constraint.technical_ref for constraint in request.inherited_constraints}
    if not mandatory <= set(refs):
        raise TechnicalBindingV2ResponseError("stage 2 must include inherited mandatory refs")
    return TechnicalBindingSelection(request.behavior.ref, refs, payload["rationale"].strip(), _evidence(payload, request))

def _object(text, required):
    try:
        payload = json.loads(_normalise(text))
    except json.JSONDecodeError as error:
        raise TechnicalBindingV2ResponseError(str(error)) from error
    if not isinstance(payload, dict) or set(payload) != required:
        raise TechnicalBindingV2ResponseError("response has unexpected or missing fields")
    return payload

def _behavior_and_rationale(payload, request):
    if payload["behavior_ref"] != request.behavior.ref:
        raise TechnicalBindingV2ResponseError("behavior_ref must equal request behavior")
    if not isinstance(payload["rationale"], str) or not payload["rationale"].strip():
        raise TechnicalBindingV2ResponseError("rationale must be non-empty text")

def _evidence(payload, request):
    value = payload["evidence_refs"]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise TechnicalBindingV2ResponseError("evidence_refs must be text list")
    refs = tuple(value)
    if len(refs) != len(set(refs)) or not set(refs) <= request.supplied_evidence_refs:
        raise TechnicalBindingV2ResponseError("evidence_refs must be supplied and unique")
    return refs

def _stage1_prompt(request):
    return json.dumps({"instruction":"Does this ONE behavior require one or more supplied existing technical candidates? Return exactly one JSON object.","behavior":_behavior(request),"technical_candidates":_candidates(request),"inherited_constraints":_constraints(request),"required_output":stage1_schema(),"rules":["do not invent anything","binding_required only if supplied candidates genuinely apply","no_binding_required if none apply","ambiguous if unsafe to decide","conflict if inherited constraints conflict","do not return technical refs"]},sort_keys=True)

def _stage2_prompt(request, stage1):
    return json.dumps({"instruction":"Select supplied technical refs that genuinely belong to this ONE behavior. Return exactly one JSON object.","stage1_status":stage1.status.value,"behavior":_behavior(request),"technical_candidates":_candidates(request),"inherited_constraints":_constraints(request),"required_output":stage2_schema(),"rules":["select only provided refs","include inherited mandatory refs","do not invent anything","do not classify roles","do not write tests or implementation"]},sort_keys=True)

def _repair_prompt(request, invalid, error, purpose):
    schema = stage1_schema() if purpose == STAGE1_PURPOSE else stage2_schema()
    return json.dumps({"task":"Format-only repair of the previous response.","behavior_ref":request.behavior.ref,"invalid_response":invalid,"validation_error":error,"required_output":schema,"rules":["return exactly one valid JSON object","preserve the previous semantic decision","do not reconsider the decision","do not add identifiers, refs, or evidence absent from the prior response"]},sort_keys=True)

def _behavior(request):
    return {"ref":request.behavior.ref,"summary":request.behavior.summary,"observable_outcome":request.behavior.observable_outcome,"source_refs":list(request.behavior.source_refs),"source_clauses":[{"ref":ref,"text":text} for ref,text in request.behavior.source_clauses]}

def _candidates(request):
    return [{"technical_ref":item.technical_ref,"kind":item.kind,"qualified_identifier":item.qualified_identifier,"origin":item.origin,"repository_evidence":item.repository_evidence,"evidence_refs":list(item.evidence_refs)} for item in request.technical_candidates]

def _constraints(request):
    return [{"technical_ref":item.technical_ref,"rationale":item.rationale} for item in request.inherited_constraints]

def stage1_schema():
    return {"type":"object","additionalProperties":False,"required":["status","behavior_ref","rationale","evidence_refs"],"properties":{"status":{"type":"string","enum":[item.value for item in BindingApplicabilityStatus]},"behavior_ref":{"type":"string"},"rationale":{"type":"string","minLength":1},"evidence_refs":{"type":"array","items":{"type":"string"}}}}

def stage2_schema():
    return {"type":"object","additionalProperties":False,"required":["behavior_ref","selected_technical_refs","rationale","evidence_refs"],"properties":{"behavior_ref":{"type":"string"},"selected_technical_refs":{"type":"array","items":{"type":"string"},"minItems":1},"rationale":{"type":"string","minLength":1},"evidence_refs":{"type":"array","items":{"type":"string"}}}}

def stage1_schema_signature():
    return sha256(json.dumps(stage1_schema(),sort_keys=True,separators=(",",":" )).encode()).hexdigest()

def stage2_schema_signature():
    return sha256(json.dumps(stage2_schema(),sort_keys=True,separators=(",",":" )).encode()).hexdigest()

def _normalise(text):
    source = text.strip()
    fence = chr(96) * 3
    if source.startswith(fence):
        lines=source.splitlines()
        if len(lines)>=3 and lines[-1].strip()==fence and lines[0].strip()[3:].strip() in {"","json"}:
            return "\n".join(lines[1:-1]).strip()
    return source
