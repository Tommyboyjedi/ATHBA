"""Deterministic boundary tests for TechnicalBindingResolver v2."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from core.development import technical_binding_resolver as v1_module
from core.development.technical_binding_resolver_v2 import (
    BindingApplicabilityStatus,
    STAGE1_PURPOSE,
    STAGE1_REPAIR_PURPOSE,
    STAGE2_PURPOSE,
    STAGE2_REPAIR_PURPOSE,
    TechnicalBindingResolverV2,
    TechnicalBindingV2ResponseError,
    _decode_stage1,
    _decode_stage2,
)
from core.development.technical_binding_resolver_qualification import (
    CONTRACT_VERSION as V1_CONTRACT_VERSION,
    load_fixtures,
)
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult

ROOT = Path(__file__).resolve().parents[2]
V1_FIXTURE_SHA256 = "c05aa8904f2bedcc2492bb5036a568043b7535f679f570f82882cd430e976e9c"
BPQ_V1_SHA256 = "3b1c2deec2369d5edc7dba79af76b5c90ea3a9b7f70b895f78237c1184300352"


class RecordingGateway:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.requests: list[ReasoningRequest] = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "local-primary", "local-primary")


def fixture(fixture_id: str = "R1"):
    return load_fixtures(ROOT)[fixture_id]


def stage1(status: str = "binding_required", fixture_id: str = "R1", **overrides: object) -> str:
    request = fixture(fixture_id).request
    payload = {"status": status, "behavior_ref": request.behavior.ref, "rationale": "Bounded supplied evidence supports this decision.", "evidence_refs": []}
    payload.update(overrides)
    return json.dumps(payload)


def stage2(fixture_id: str = "R1", refs: list[str] | None = None, **overrides: object) -> str:
    request = fixture(fixture_id).request
    payload = {"behavior_ref": request.behavior.ref, "selected_technical_refs": refs if refs is not None else ["R1-signal-board", "R1-publish", "R1-get-latest"], "rationale": "Only supplied technical candidates belong to the behavior.", "evidence_refs": []}
    payload.update(overrides)
    return json.dumps(payload)


@pytest.mark.parametrize("status", ["binding_required", "no_binding_required", "ambiguous", "conflict"])
def test_stage1_allowed_statuses_parse(status: str):
    assert _decode_stage1(stage1(status), fixture().request).status.value == status


def test_stage1_cannot_return_bindings():
    with pytest.raises(TechnicalBindingV2ResponseError):
        _decode_stage1(stage1(bindings=[]), fixture().request)


@pytest.mark.parametrize("status", ["no_binding_required", "ambiguous", "conflict"])
def test_stage2_does_not_run_after_nonbinding_stage1_status(status: str):
    gateway = RecordingGateway([stage1(status)])
    result = asyncio.run(TechnicalBindingResolverV2(gateway).resolve(fixture().request))
    assert result.stage2 is None
    assert [item.purpose for item in gateway.requests] == [STAGE1_PURPOSE]


def test_stage2_valid_supplied_refs_parse():
    assert _decode_stage2(stage2(), fixture().request).selected_technical_refs == ("R1-signal-board", "R1-publish", "R1-get-latest")


@pytest.mark.parametrize("refs", [["invented"], ["R1-signal-board", "R1-signal-board"], []])
def test_stage2_rejects_unknown_duplicate_and_empty_selection(refs: list[str]):
    with pytest.raises(TechnicalBindingV2ResponseError):
        _decode_stage2(stage2(refs=refs), fixture().request)


def test_stage2_rejects_omitted_inherited_mandatory_ref():
    with pytest.raises(TechnicalBindingV2ResponseError, match="inherited"):
        _decode_stage2(stage2("R3", ["R3-reservation-book"]), fixture("R3").request)


def test_invented_identifier_is_not_accepted():
    with pytest.raises(TechnicalBindingV2ResponseError):
        _decode_stage2(stage2(refs=["audit_timestamp"]), fixture().request)


def test_at_most_one_format_only_repair_per_stage():
    stage1_gateway = RecordingGateway(["not json", "still not json"])
    stage1_result = asyncio.run(TechnicalBindingResolverV2(stage1_gateway).resolve(fixture().request))
    assert stage1_result.stage1.status is BindingApplicabilityStatus.PROTOCOL_FAILURE
    assert [item.purpose for item in stage1_gateway.requests] == [STAGE1_PURPOSE, STAGE1_REPAIR_PURPOSE]
    stage2_gateway = RecordingGateway([stage1(), "not json", stage2()])
    stage2_result = asyncio.run(TechnicalBindingResolverV2(stage2_gateway).resolve(fixture().request))
    assert stage2_result.stage2_trace is not None and stage2_result.stage2_trace.repair_count == 1
    assert [item.purpose for item in stage2_gateway.requests] == [STAGE1_PURPOSE, STAGE2_PURPOSE, STAGE2_REPAIR_PURPOSE]


def test_semantic_retry_is_not_performed():
    gateway = RecordingGateway([stage1("no_binding_required")])
    asyncio.run(TechnicalBindingResolverV2(gateway).resolve(fixture().request))
    assert len(gateway.requests) == 1


def test_resolver_has_no_repository_or_product_integration():
    source = (ROOT / "core/development/technical_binding_resolver_v2.py").read_text(encoding="utf-8")
    assert not any(token in source for token in ("open(", "Path(", "subprocess", "behavior_planner", "strict_tdd", "ScenarioDraft", "ObservationResolver"))


def test_v1_and_bpq_v1_remain_immutable_and_observation_resolver_is_absent():
    assert V1_CONTRACT_VERSION == "technical-binding-resolver-v1"
    assert hashlib.sha256((ROOT / "tests/fixtures/technical_binding_resolver_v1.json").read_bytes()).hexdigest() == V1_FIXTURE_SHA256
    assert hashlib.sha256((ROOT / "qualification_fixtures/behavior_planner_qualification_v1.json").read_bytes()).hexdigest() == BPQ_V1_SHA256
    assert not hasattr(v1_module, "ObservationResolver")
