"""Deterministic contract tests for the isolated TechnicalBindingResolver."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core.development import technical_binding_resolver as resolver_module
from core.development.technical_binding_resolver import (
    TechnicalBindingResolutionDecoder, TechnicalBindingResolutionStatus, TechnicalBindingResolver,
    TechnicalBindingResponseError,
)
from core.development.technical_binding_resolver_qualification import FIXTURE_PATH, load_fixtures
from core.execution.reasoning_gateway import ReasoningResult

ROOT = Path(__file__).resolve().parents[2]

class RecordingGateway:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.requests = []
    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "local-primary", "local-primary")

def fixture(name: str = "R1"):
    return load_fixtures(ROOT)[name]

def response(fixture_id: str = "R1", **overrides: object) -> str:
    item = fixture(fixture_id)
    payload = {
        "status": item.expected.status.value,
        "behavior_ref": item.request.behavior.ref,
        "bindings": [{"technical_ref": binding.technical_ref, "role": binding.role.value} for binding in item.expected.bindings],
        "rationale": "Supplied evidence supports this bounded resolution.",
        "evidence_refs": [item.request.behavior.source_refs[0]] if item.expected.status.value == "resolved" else [],
    }
    payload.update(overrides)
    return json.dumps(payload)

def decode(payload: str, fixture_id: str = "R1"):
    return TechnicalBindingResolutionDecoder().decode(payload, fixture(fixture_id).request)

def test_valid_resolved_output_parses():
    result = decode(response())
    assert result.status is TechnicalBindingResolutionStatus.RESOLVED
    assert len(result.bindings) == 3

def test_unknown_technical_ref_is_rejected():
    with pytest.raises(TechnicalBindingResponseError):
        decode(response(bindings=[{"technical_ref": "invented", "role": "subject"}]))

def test_invalid_role_is_rejected():
    with pytest.raises(TechnicalBindingResponseError):
        decode(response(bindings=[{"technical_ref": "R1-signal-board", "role": "invented"}]))

def test_duplicate_binding_is_rejected():
    with pytest.raises(TechnicalBindingResponseError):
        decode(response(bindings=[{"technical_ref": "R1-signal-board", "role": "subject"}, {"technical_ref": "R1-signal-board", "role": "action"}]))

def test_resolved_with_zero_bindings_is_rejected():
    with pytest.raises(TechnicalBindingResponseError):
        decode(response(bindings=[]))

def test_no_binding_required_with_bindings_is_rejected():
    with pytest.raises(TechnicalBindingResponseError):
        decode(response("R4", bindings=[{"technical_ref": "R4-approve", "role": "action"}]), "R4")

@pytest.mark.parametrize("status", ["ambiguous", "conflict"])
def test_ambiguous_and_conflict_cannot_create_authoritative_bindings(status: str):
    with pytest.raises(TechnicalBindingResponseError):
        decode(response(status=status, bindings=[{"technical_ref": "R1-publish", "role": "action"}]))

def test_behavior_ref_mismatch_is_rejected():
    with pytest.raises(TechnicalBindingResponseError):
        decode(response(behavior_ref="other-behavior"))

def test_model_cannot_invent_technical_identifier():
    with pytest.raises(TechnicalBindingResponseError, match="supplied candidate"):
        decode(response(bindings=[{"technical_ref": "record_audit", "role": "action"}]))

def test_one_format_only_repair_maximum():
    gateway = RecordingGateway(["not json", "still not json"])
    trace = asyncio.run(TechnicalBindingResolver(gateway).resolve_with_trace(fixture().request))
    assert trace.resolution.status is TechnicalBindingResolutionStatus.PROTOCOL_FAILURE
    assert trace.format_repair_count == 1
    assert [request.purpose for request in gateway.requests] == [
        "athba_technical_binding_resolution", "athba_technical_binding_resolution_json_repair"
    ]

def test_semantic_retry_is_not_performed():
    gateway = RecordingGateway([response(status="no_binding_required", bindings=[])])
    trace = asyncio.run(TechnicalBindingResolver(gateway).resolve_with_trace(fixture().request))
    assert trace.resolution.status is TechnicalBindingResolutionStatus.NO_BINDING_REQUIRED
    assert len(gateway.requests) == 1

def test_resolver_does_not_mutate_repository():
    source = (ROOT / "core/development/technical_binding_resolver.py").read_text(encoding="utf-8")
    assert "open(" not in source and "Path(" not in source and "subprocess" not in source

def test_resolver_does_not_alter_behavior_planner_or_tdd_state():
    source = (ROOT / "core/development/technical_binding_resolver.py").read_text(encoding="utf-8")
    assert "behavior_planner" not in source and "strict_tdd" not in source and "ScenarioDraft" not in source

def test_qualification_fixtures_are_separate_from_behavior_planner_qualification():
    payload = (ROOT / FIXTURE_PATH).read_text(encoding="utf-8")
    assert "BPQ" not in payload and "behavior planner" not in payload.lower()
    assert tuple(load_fixtures(ROOT)) == ("R1", "R2", "R3", "R4")

def test_bpq_v1_is_not_a_resolver_fixture():
    assert "behavior_planner" not in str(FIXTURE_PATH)

def test_no_observation_resolver_is_restored():
    assert not hasattr(resolver_module, "ObservationResolver")

def test_inherited_binding_must_be_preserved():
    with pytest.raises(TechnicalBindingResponseError, match="inherited"):
        decode(response("R3", bindings=[{"technical_ref": "R3-reservation-book", "role": "subject"}]), "R3")
