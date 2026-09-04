"""Deterministic boundary tests for TechnicalBindingResolver v3."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from core.development import technical_binding_resolver as v1_module
from core.development import technical_binding_resolver_v2 as v2_module
from core.development import technical_binding_resolver_v3 as v3_module
from core.development.technical_binding_resolver_v3 import (
    REPAIR_PURPOSE,
    SELECTION_PURPOSE,
    TechnicalBindingResolverV3,
    TechnicalBindingV3ResponseError,
    TechnicalBindingSelectionV3,
    decode_selection,
    expand_owners,
)
from core.development.technical_binding_resolver_v3_qualification import (
    CONTRACT_VERSION,
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

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "local-primary", "local-primary")


def fixture(fixture_id: str = "R2"):
    return load_fixtures(ROOT)[fixture_id]


def response(fixture_id: str = "R2", refs: list[str] | None = None, **overrides: object) -> str:
    request = fixture(fixture_id).request
    expected = list(fixture(fixture_id).expected_selected_refs) if refs is None else refs
    payload = {"behavior_ref": request.behavior.behavior_ref, "selected_refs": expected}
    payload.update(overrides)
    return json.dumps(payload)


def test_valid_single_selection_parses():
    assert decode_selection(response(), fixture().request).selected_refs == ("R2-find-customer",)


def test_valid_multiple_selection_parses():
    assert decode_selection(response("R1"), fixture("R1").request).selected_refs == ("R1-publish", "R1-get-latest")


def test_valid_empty_selection_parses():
    assert decode_selection(response("R4"), fixture("R4").request).selected_refs == ()


@pytest.mark.parametrize("refs", [["invented"], ["R2-find-customer", "R2-find-customer"]])
def test_unknown_and_duplicate_refs_are_rejected(refs: list[str]):
    with pytest.raises(TechnicalBindingV3ResponseError):
        decode_selection(response(refs=refs), fixture().request)


def test_mandatory_ref_omission_is_rejected():
    with pytest.raises(TechnicalBindingV3ResponseError, match="mandatory"):
        decode_selection(response("R3", []), fixture("R3").request)


def test_behavior_ref_mismatch_and_invented_identifier_are_rejected():
    with pytest.raises(TechnicalBindingV3ResponseError):
        decode_selection(response(behavior_ref="other"), fixture().request)
    with pytest.raises(TechnicalBindingV3ResponseError):
        decode_selection(response(refs=["ApprovalService.audit_timestamp"]), fixture().request)


def test_only_one_format_repair_is_permitted():
    gateway = RecordingGateway(["not json", "still not json"])
    resolution = asyncio.run(TechnicalBindingResolverV3(gateway).resolve(fixture().request))
    assert resolution.selection is None
    assert resolution.trace.format_repair_count == 1
    assert [request.purpose for request in gateway.requests] == [SELECTION_PURPOSE, REPAIR_PURPOSE]
    assert gateway.requests[1].prompt == "Return the same selection in the required JSON shape."


def test_semantic_retry_is_not_performed():
    gateway = RecordingGateway([response("R4")])
    resolution = asyncio.run(TechnicalBindingResolverV3(gateway).resolve(fixture("R4").request))
    assert resolution.selection is not None
    assert len(gateway.requests) == 1


def test_owner_expansion_derives_customer_and_reservation_owners():
    customer = decode_selection(response("R2"), fixture("R2").request)
    reservation = decode_selection(response("R3"), fixture("R3").request)
    assert expand_owners(fixture("R2").request, customer).owner_qualified_identifiers == ("CustomerRepository",)
    assert expand_owners(fixture("R3").request, reservation).owner_qualified_identifiers == ("ReservationBook",)


def test_owner_expansion_handles_empty_and_deduplicates_owners_without_new_methods():
    empty = decode_selection(response("R4"), fixture("R4").request)
    assert expand_owners(fixture("R4").request, empty).owner_qualified_identifiers == ()
    selection = TechnicalBindingSelectionV3(fixture("R1").request.behavior.behavior_ref, ("R1-publish", "R1-get-latest"))
    expansion = expand_owners(fixture("R1").request, selection)
    assert expansion.owner_qualified_identifiers == ("SignalBoard",)
    assert expansion.selected_refs == selection.selected_refs


def test_v1_v2_and_bpq_v1_remain_intact_without_observation_resolver():
    assert CONTRACT_VERSION == "technical-binding-resolver-v3"
    assert hashlib.sha256((ROOT / "tests/fixtures/technical_binding_resolver_v1.json").read_bytes()).hexdigest() == V1_FIXTURE_SHA256
    assert hashlib.sha256((ROOT / "qualification_fixtures/behavior_planner_qualification_v1.json").read_bytes()).hexdigest() == BPQ_V1_SHA256
    assert (ROOT / "core/development/technical_binding_resolver_v2.py").is_file()
    assert not hasattr(v1_module, "ObservationResolver")
    assert not hasattr(v2_module, "ObservationResolver")
    assert not hasattr(v3_module, "ObservationResolver")


def test_v3_has_no_repository_or_downstream_integration():
    source = (ROOT / "core/development/technical_binding_resolver_v3.py").read_text(encoding="utf-8")
    forbidden = ("open(", "Path(", "subprocess", "behavior_planner", "strict_tdd", "ScenarioDraft", "ObservationResolver")
    assert not any(token in source for token in forbidden)
