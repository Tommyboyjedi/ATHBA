"""Fake-only response-boundary regressions for Behavior Requirement replanning."""
import json

import pytest

from core.development.behavior_replanning import BehaviorRequirementReplanner, BehaviorReplanFailure
from core.development.behavior_replan_domain import BehaviorReplanBlocker, BehaviorReplanDisposition
from tests.development.test_behavior_replanning import pending_application, split_payload, request


def fenced(raw):
    return "```json\n" + raw + "\n```"


@pytest.mark.asyncio
@pytest.mark.parametrize("use_fence", [False, True])
async def test_valid_response_is_accepted_with_one_submission(tmp_path, use_fence):
    app, gateway, _, _, _, _ = await pending_application(tmp_path)
    replan_request = app.states.load("feature").behavior_replans[0].request
    raw = json.dumps(split_payload(replan_request.parent.to_dict()))
    gateway.payload = fenced(raw) if use_fence else raw
    result = await BehaviorRequirementReplanner(gateway).replan(replan_request)
    assert result.disposition == BehaviorReplanDisposition.SPLIT
    assert len(result.children) == 2
    assert result.raw_response == gateway.payload
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", [
    "historical_wrapper", "nested_object", "role", "unsplittable_children",
    "prose_before", "prose_after", "prose_around_fence", "double_fence",
    "missing_close", "missing_open", "wrong_language", "two_objects", "array",
])
async def test_invalid_envelopes_fail_without_extraction_or_retry(tmp_path, shape):
    app, gateway, _, _, _, _ = await pending_application(tmp_path)
    replan_request = app.states.load("feature").behavior_replans[0].request
    payload = split_payload(replan_request.parent.to_dict())
    raw = json.dumps(payload)
    variants = {
        "historical_wrapper": fenced(json.dumps({
            "role": "Behavior Planner", "response_contract": payload, "unsplittable_children": [],
        })),
        "nested_object": json.dumps({"response_contract": payload}),
        "role": fenced(json.dumps({**payload, "role": "Behavior Planner"})),
        "unsplittable_children": fenced(json.dumps({**payload, "unsplittable_children": []})),
        "prose_before": "Here is the answer:\n" + raw,
        "prose_after": raw + "\nThat is the answer.",
        "prose_around_fence": "Answer:\n" + fenced(raw) + "\nDone.",
        "double_fence": fenced(fenced(raw)),
        "missing_close": "```json\n" + raw,
        "missing_open": raw + "\n```",
        "wrong_language": "```python\n" + raw + "\n```",
        "two_objects": fenced(raw + "\n" + raw),
        "array": json.dumps([payload]),
    }
    gateway.payload = variants[shape]
    with pytest.raises(BehaviorReplanFailure) as failure:
        await BehaviorRequirementReplanner(gateway).replan(replan_request)
    assert failure.value.kind == BehaviorReplanBlocker.PROTOCOL_FAILURE
    assert failure.value.raw_response == gateway.payload
    if shape in {"historical_wrapper", "nested_object", "role", "unsplittable_children"}:
        assert "exact response contract" in failure.value.detail
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_provider_failure_is_not_retried(tmp_path):
    app, gateway, _, _, _, _ = await pending_application(tmp_path)
    gateway.payload = RuntimeError("provider unavailable")
    replan_request = app.states.load("feature").behavior_replans[0].request
    with pytest.raises(BehaviorReplanFailure) as failure:
        await BehaviorRequirementReplanner(gateway).replan(replan_request)
    assert failure.value.kind == BehaviorReplanBlocker.PROVIDER_FAILURE
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
async def test_prompt_makes_only_permitted_output_explicit(tmp_path):
    app, gateway, _, _, _, _ = await pending_application(tmp_path)
    replan_request = app.states.load("feature").behavior_replans[0].request
    await BehaviorRequirementReplanner(gateway).replan(replan_request)
    prompt = json.loads(gateway.requests[0].prompt)
    rules = "\n".join(prompt["output_rules"])
    for rule in (
        "return raw JSON only", "return exactly one JSON object", "no Markdown",
        "no code fences", "no commentary", "do not echo the prompt",
        "do not return response_contract", "do not return role",
        "do not return request", "do not return unsplittable_children",
        "top-level keys must be exactly: disposition, rationale, children, coverage_rationale",
    ):
        assert rule in rules
    assert set(prompt["required_output_schema"]) == {
        "disposition", "rationale", "children", "coverage_rationale",
    }
    assert "response_contract" not in prompt
    assert "unsplittable_children" not in prompt
    assert len(gateway.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["same_parent", "source", "coverage", "one_child", "narrowing"])
async def test_fence_normalization_does_not_bypass_split_validation(tmp_path, invalid):
    app, gateway, _, scenarios, reconciler, _ = await pending_application(tmp_path)
    parent = app.states.load("feature").behavior_replans[0].request.parent.to_dict()
    payload = split_payload(parent)
    if invalid == "same_parent":
        payload["children"][0]["observable_outcome"] = parent["observable_outcome"]
    elif invalid == "source":
        payload["children"][0]["source_refs"] = ["invented"]
    elif invalid == "coverage":
        payload["coverage_rationale"] = ""
    elif invalid == "one_child":
        payload["children"] = payload["children"][:1]
    else:
        payload["children"][0]["narrowing_rationale"] = ""
    gateway.payload = fenced(json.dumps(payload))
    count = len(scenarios.requests)
    result = await app.run(request())
    assert result.current_status == "blocked"
    assert len(gateway.requests) == 1
    assert len(scenarios.requests) == count
    assert reconciler.calls == []
