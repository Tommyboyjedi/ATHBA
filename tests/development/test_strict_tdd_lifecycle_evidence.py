from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest

from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.strict_tdd_lifecycle_evidence import (
    LifecycleEventAppendRequest,
    LifecycleEventDraft,
    NoOpStrictTddLifecycleEventSink,
    PersistingLifecycleEventSinkDependencies,
    PersistingStrictTddLifecycleEventSink,
    StrictTddLifecycleEvent,
    StrictTddLifecycleEventKind,
    StrictTddLifecycleEventRepository,
    StrictTddLifecycleRunContext,
    StrictTddLifecycleStatus,
    StrictTddProofReportBuilder,
    StrictTddProofReportInput,
)


def context() -> StrictTddLifecycleRunContext:
    return StrictTddLifecycleRunContext("run-one", "project-one", "increment a value", "athba-test", "rack-test")


def event(number: int = 0, event_id: str = "event-one") -> StrictTddLifecycleEvent:
    return StrictTddLifecycleEvent(event_id, number, datetime(2026, 9, 1, tzinfo=UTC), "run-one", "project-one", StrictTddLifecycleEventKind.RUN_STARTED, StrictTddLifecycleStatus.STARTED, ("evidence://one",))


def test_event_round_trip_and_typed_kind() -> None:
    restored = StrictTddLifecycleEvent.from_dict(event().to_dict())
    assert restored == event()
    assert isinstance(restored.event_kind, StrictTddLifecycleEventKind)


def test_event_rejects_non_utc_timestamp() -> None:
    with pytest.raises(ValueError, match="UTC-aware"):
        StrictTddLifecycleEvent("event", 0, datetime.now(timezone.utc).replace(tzinfo=None), "run", "project", StrictTddLifecycleEventKind.RUN_STARTED, StrictTddLifecycleStatus.STARTED, ("evidence://one",))


def test_store_round_trip_idempotency_and_reload(tmp_path) -> None:
    store = StrictTddLifecycleEventRepository(tmp_path)
    request = LifecycleEventAppendRequest(context(), event())
    assert store.append(request) == event()
    assert store.append(request) == event()
    assert StrictTddLifecycleEventRepository(tmp_path).events(context()) == (event(),)


def test_store_rejects_conflicting_sequence_and_event_id(tmp_path) -> None:
    store = StrictTddLifecycleEventRepository(tmp_path)
    store.append(LifecycleEventAppendRequest(context(), event()))
    with pytest.raises(ValueError, match="sequence"):
        store.append(LifecycleEventAppendRequest(context(), event(0, "other")))
    with pytest.raises(ValueError, match="event id"):
        store.append(LifecycleEventAppendRequest(context(), event(1, "event-one")))


def test_store_fails_closed_for_truncated_record(tmp_path) -> None:
    store = StrictTddLifecycleEventRepository(tmp_path)
    store.append(LifecycleEventAppendRequest(context(), event()))
    path = next(tmp_path.glob("lifecycle-runs/*/events.jsonl"))
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="truncated"):
        store.events(context())


def test_runs_are_isolated_and_noop_persists_nothing(tmp_path) -> None:
    store = StrictTddLifecycleEventRepository(tmp_path)
    assert NoOpStrictTddLifecycleEventSink().record(LifecycleEventDraft("ignored", StrictTddLifecycleEventKind.RUN_STARTED, StrictTddLifecycleStatus.STARTED, ("evidence://one",))) is None
    other = StrictTddLifecycleRunContext("run-two", "project-two", "same requirement", "athba-test", "rack-test")
    store.append(LifecycleEventAppendRequest(context(), event()))
    assert store.events(other) == ()


def test_persisting_sink_assigns_sequences_and_preserves_shas(tmp_path) -> None:
    sink = PersistingStrictTddLifecycleEventSink(PersistingLifecycleEventSinkDependencies(StrictTddLifecycleEventRepository(tmp_path), context()))
    recorded = sink.record(LifecycleEventDraft("event-two", StrictTddLifecycleEventKind.FRONTIER_RED_ACCEPTED, StrictTddLifecycleStatus.ACCEPTED, ("evidence://two",), scenario_id="scenario", frontier_index=0, canonical_ref="refs/heads/main", canonical_revision="a" * 40, working_ref="refs/heads/work", working_revision="b" * 40))
    assert recorded.sequence_number == 0
    assert recorded.canonical_revision == "a" * 40
    assert recorded.working_revision == "b" * 40


def test_report_is_deterministic_incomplete_and_secret_safe() -> None:
    input_value = StrictTddProofReportInput(context(), None, (), (), (event(),))
    first = StrictTddProofReportBuilder().build(input_value)
    assert first == StrictTddProofReportBuilder().build(input_value)
    assert "unavailable/incomplete" in first.markdown
    with pytest.raises(ValueError, match="secret"):
        StrictTddLifecycleRunContext("run", "project", "api_key=secret", "athba", "rack")


def test_completed_report_includes_final_reconciliation() -> None:
    state = StrictTddFeatureState("project-one", "hash", "completed", final_reconciliation=({"answer": "NO"},))
    report = StrictTddProofReportBuilder().build(StrictTddProofReportInput(context(), state, (), (), ()))
    assert report.structured["sections"]["run"]["final_status"] == "completed"
    assert report.structured["sections"]["final_reconciliation"]["available"] is True
