import json

import pytest

from core.development.behavior_contract_surface import DeclaredProductSurface
from core.development.scenario_observation_support import (
    ScenarioObservationContext,
    ScenarioObservationRequirement,
    ScenarioObservationResolver,
    ScenarioObservationSupport,
    ScenarioObservationSupportStatus,
)
from core.development.specification_domain import SourceRequirementClause
from core.execution.reasoning_gateway import ReasoningResult


class FakeReasoningGateway:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def reason(self, request):
        self.requests.append(request)
        return ReasoningResult(self.responses.pop(0), "fake", "fake")


def context():
    return ScenarioObservationContext(
        "REQ-002",
        "record stores value for name",
        "value is stored for the supplied name",
        "record then demonstrate the stored value",
        (SourceRequirementClause("SRC-002", "record stores value", "behavior"),),
        DeclaredProductSurface(
            "EntryStore",
            frozenset({"record", "latest", "delete"}),
            canonical_members=("record(name, value)", "latest(name)", "delete(name)"),
        ),
        (
            ScenarioObservationRequirement("REQ-002", "record stores value", "value is stored"),
            ScenarioObservationRequirement("REQ-003", "latest returns stored value", "returns newest"),
            ScenarioObservationRequirement("REQ-004", "delete removes value", "removes value"),
        ),
    )


def response(status, selected=(), evidence=("REQ-002",)):
    return json.dumps({"status": status, "selected_members": list(selected), "evidence_refs": list(evidence)})


@pytest.mark.asyncio
async def test_selects_only_declared_minimal_observation_member():
    gateway = FakeReasoningGateway([response("support_selected", ("latest(name)",))])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.SUPPORT_SELECTED.value
    assert support.selected_members == ("latest(name)",)
    assert support.response_attempts == 1
    prompt = gateway.requests[0].prompt
    assert "delete(name)" in prompt
    assert "gatekeeper" not in prompt.lower()


@pytest.mark.asyncio
async def test_self_observable_resolution_needs_no_support():
    gateway = FakeReasoningGateway([response("not_required")])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.NOT_REQUIRED.value
    assert support.selected_members == ()


@pytest.mark.asyncio
async def test_no_legitimate_observer_is_durable_unresolvable():
    gateway = FakeReasoningGateway([response("unresolvable")])

    support = await ScenarioObservationResolver(gateway).resolve(context())
    restored = ScenarioObservationSupport.from_dict(support.to_dict())

    assert restored == support
    assert restored.status == ScenarioObservationSupportStatus.UNRESOLVABLE.value


@pytest.mark.asyncio
async def test_invalid_json_receives_one_format_only_repair():
    gateway = FakeReasoningGateway(["not JSON", response("support_selected", ("latest(name)",))])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.response_attempts == 2
    assert [item.purpose for item in gateway.requests] == [
        "athba_scenario_observation_support",
        "athba_scenario_observation_support_json_repair",
    ]
    assert "second semantic decision" in gateway.requests[1].prompt


@pytest.mark.asyncio
async def test_undeclared_selection_fails_closed_after_one_repair():
    gateway = FakeReasoningGateway([
        response("support_selected", ("private_get(name)",)),
        response("support_selected", ("private_get(name)",)),
    ])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.PROTOCOL_FAILURE.value
    assert support.selected_members == ()
    assert support.protocol_failure is not None
    assert support.response_attempts == 2


@pytest.mark.asyncio
async def test_unknown_requirement_evidence_fails_closed():
    gateway = FakeReasoningGateway([
        response("support_selected", ("latest(name)",), ("REQ-999",)),
        response("support_selected", ("latest(name)",), ("REQ-999",)),
    ])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.PROTOCOL_FAILURE.value


def test_decoder_accepts_only_one_ordinary_json_fence():
    from core.development.scenario_observation_support import _decode

    decoded = _decode('```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```')

    assert decoded.status == "not_required"


@pytest.mark.parametrize("source", [
    'prose {"status":"not_required","selected_members":[],"evidence_refs":[]}',
    '```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```\n```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```',
])
def test_decoder_rejects_ambiguous_non_fence_responses(source):
    from core.development.scenario_observation_support import _decode

    with pytest.raises(ValueError):
        _decode(source)


@pytest.mark.parametrize(
    "source",
    [
        '{"status":"not_required","selected_members":[],"evidence_refs":[]}',
        '```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```',
        '```\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```',
    ],
)
def test_decoder_accepts_one_raw_or_bounded_fenced_object(source):
    from core.development.scenario_observation_support import _decode

    assert _decode(source).status == "not_required"


@pytest.mark.parametrize(
    "source",
    [
        'prose {"status":"not_required","selected_members":[],"evidence_refs":[]}',
        'before\n```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```',
        '```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```\nafter',
        '```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```\n```json\n{"status":"not_required","selected_members":[],"evidence_refs":[]}\n```',
        '{"status":"not_required","selected_members":[],"evidence_refs":[]} {"status":"not_required","selected_members":[],"evidence_refs":[]}',
    ],
)
def test_decoder_rejects_prose_and_multiple_objects_without_extraction(source):
    from core.development.scenario_observation_support import _decode

    with pytest.raises(ValueError):
        _decode(source)


@pytest.mark.asyncio
async def test_fenced_format_repair_is_accepted_without_second_semantic_decision():
    gateway = FakeReasoningGateway([
        "malformed initial response",
        '```json\n{"status":"support_selected","selected_members":["latest(name)"],"evidence_refs":["REQ-002"]}\n```',
    ])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.SUPPORT_SELECTED.value
    assert support.selected_members == ("latest(name)",)
    assert support.response_attempts == 2
    assert [request.purpose for request in gateway.requests] == [
        "athba_scenario_observation_support",
        "athba_scenario_observation_support_json_repair",
    ]
    assert "second semantic decision" in gateway.requests[1].prompt


@pytest.mark.asyncio
async def test_double_invalid_response_fails_closed_after_one_repair_only():
    gateway = FakeReasoningGateway(["not JSON", "still not JSON"])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.PROTOCOL_FAILURE.value
    assert support.selected_members == ()
    assert support.protocol_failure is not None
    assert support.response_attempts == 2
    assert [request.purpose for request in gateway.requests] == [
        "athba_scenario_observation_support",
        "athba_scenario_observation_support_json_repair",
    ]


@pytest.mark.asyncio
async def test_private_selection_fails_closed_without_changing_canonical_policy():
    private = response("support_selected", ("_latest(name)",))
    gateway = FakeReasoningGateway([private, private])

    support = await ScenarioObservationResolver(gateway).resolve(context())

    assert support.status == ScenarioObservationSupportStatus.PROTOCOL_FAILURE.value
    assert support.response_attempts == 2
