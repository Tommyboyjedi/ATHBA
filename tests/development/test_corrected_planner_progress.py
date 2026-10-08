"""Corrected Planner responses must reach the existing full validation transition."""
from copy import deepcopy
import pytest
from core.development.strict_tdd_transitions import FeatureTransitionKind
from tests.development.test_behavior_replanning import pending_application, request, split_payload

@pytest.mark.asyncio
@pytest.mark.parametrize("valid_correction", [True, False])
async def test_corrected_received_response_is_durable_progress_before_validation(tmp_path, valid_correction):
    app, gateway, _, _, _, _ = await pending_application(tmp_path)
    record = app.states.load("feature").behavior_replans[-1]
    original = split_payload(record.request.parent.to_dict())
    original["children"][0]["observable_outcome"] = record.request.parent.observable_outcome
    corrected = split_payload(record.request.parent.to_dict()) if valid_correction else deepcopy(original)
    gateway.payload = [original, corrected]
    first = await app.advance(request())
    assert first.kind == FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED
    correction = await app.advance(request())
    assert correction.kind == FeatureTransitionKind.BEHAVIOR_SPLIT_RECEIVED
    assert first.fingerprint != correction.fingerprint, "The normal run controller must not mistake one corrective submission for a stalled transition"
    state = app.states.load("feature")
    assert state.behavior_replans[-1].correction_attempted
    assert len(state.behavior_replans[-1].request.tester_failures.attempts) == 4
    assert len(gateway.requests) == 2
    # Load/save is the production JSON persistence boundary; no resubmission on resume.
    app.states.save(state)
    validation = await app.advance(request())
    assert validation.kind == (FeatureTransitionKind.BEHAVIOR_SPLIT if valid_correction else FeatureTransitionKind.BLOCKED)
    assert len(gateway.requests) == 2
    if not valid_correction:
        assert app.states.load("feature").behavior_replans[-1].detail.startswith("proposal correction exhausted:")
