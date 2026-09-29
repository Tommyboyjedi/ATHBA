"""Keep fake reservation deadlines deterministic without weakening production."""
from dataclasses import replace
import time as real_time

import pytest

from core import atomic_json_file
from core.execution import rack_ai_reservation as reservation_source
from core.execution.rack_ai_runtime import RackAiResourceWait
from tests.execution.test_rack_ai_runtime_reservations import operations, session


@pytest.mark.parametrize("terminal", ["expired", "released", "cancelled", "preempted"])
@pytest.mark.parametrize("controlled", [False, True], ids=["real-clock-reproduction", "controlled-clock"])
def test_slow_durable_writes_only_exhaust_the_real_fixture_clock(
    tmp_path, monkeypatch, reservation_poll_clock, terminal, controlled
):
    reservation, client, store = session(tmp_path)
    reservation.ready("local-coder")
    previous = store.load_reservation("campaign")
    client.reservations["R1"]["services"]["local-primary"]["state"] = terminal
    if not controlled:
        monkeypatch.setattr(reservation_source, "time", real_time)
    flushed = []
    original_fsync_directory = atomic_json_file._fsync_directory

    def slow_fsync_directory(directory):
        original_fsync_directory(directory)
        flushed.append(directory)
        # Deliberately exceed the existing 2 ms fixture budget. The original
        # file AND directory fsync still run; no durability check is disabled.
        real_time.sleep(0.01)

    monkeypatch.setattr(atomic_json_file, "_fsync_directory", slow_fsync_directory)
    if not controlled:
        with pytest.raises(RackAiResourceWait, match="resource wait bound reached"):
            reservation.ready("local-primary")
        assert len(operations(client, "reserve")) == 1
        assert len(operations(client, "release_reservation")) == 1
        assert flushed
        return

    assert reservation.ready("local-primary")["reservation_id"] == "R2"
    current = store.load_reservation("campaign")
    assert current.acquisition_id != previous.acquisition_id
    assert current.priority == previous.priority == "low"
    lifecycle = [call["operation"] for call in client.calls
                 if call["operation"] in {"reserve", "release_reservation"}]
    assert lifecycle == ["reserve", "release_reservation", "reserve"]
    assert not operations(client, "submit_work")
    assert not operations(client, "refresh_reservation")
    assert store.load("campaign").total_application_transition_count == 0
    assert current.pending_workspace is None and current.pending_inference is None
    assert reservation_poll_clock.sleeps == [client.configuration.poll_seconds]
    assert flushed


def test_controlled_clock_still_enforces_resource_deadline(tmp_path, reservation_poll_clock):
    reservation, client, store = session(tmp_path, {"local-primary": "preparing"})
    with pytest.raises(RackAiResourceWait, match="preparing; resource wait bound reached"):
        reservation.ready("local-primary")
    assert reservation_poll_clock.elapsed == pytest.approx(client.configuration.resource_wait_seconds)
    assert reservation_poll_clock.sleeps == pytest.approx([0.001, 0.001])
    assert len(operations(client, "reserve")) == 1
    assert not operations(client, "submit_work")
    assert store.load("campaign").total_application_transition_count == 0


def test_retry_after_is_honoured_and_clamped_to_deadline(tmp_path, reservation_poll_clock):
    reservation, client, _ = session(tmp_path, {"local-primary": "preparing"})
    client.configuration = replace(client.configuration, resource_wait_seconds=0.005)

    def retry_after(view):
        view["retry_after"] = 0.003

    client.inspect_hook = retry_after
    with pytest.raises(RackAiResourceWait, match="resource wait bound reached"):
        reservation.ready("local-primary")
    assert reservation_poll_clock.sleeps == pytest.approx([0.003, 0.002])
    assert reservation_poll_clock.elapsed == pytest.approx(0.005)
    assert len(operations(client, "reserve")) == 1


def test_controlled_deadline_does_not_replace_shared_time(reservation_poll_clock):
    assert reservation_source.time is reservation_poll_clock
    assert real_time.monotonic.__module__ == "time"
    assert real_time.sleep.__module__ == "time"


def test_other_tests_keep_production_clock_after_fixture_teardown():
    assert reservation_source.time is real_time
