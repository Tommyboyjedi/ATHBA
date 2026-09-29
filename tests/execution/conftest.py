"""Clocks for fake-runtime tests; production timing and persistence stay real."""
from __future__ import annotations

from math import isfinite

import pytest


class ReservationPollClock:
    """Only requested sleeps advance time; host I/O cannot consume test budgets."""

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.sleeps: list[float] = []
        self.reads = 0

    def monotonic(self) -> float:
        self.reads += 1
        if self.reads > 10000:
            raise AssertionError("reservation polling did not converge")
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        if not isfinite(seconds) or seconds <= 0:
            raise AssertionError("poll sleep must advance by a finite positive duration")
        self.sleeps.append(seconds)
        self.elapsed += seconds


@pytest.fixture
def reservation_poll_clock(monkeypatch):
    from core.execution import rack_ai_reservation

    clock = ReservationPollClock()
    # Replace this module's reference, not attributes on Python's shared time
    # module. Other threads, workspace deadlines and real fsync are untouched.
    monkeypatch.setattr(rack_ai_reservation, "time", clock)
    return clock


@pytest.fixture(autouse=True)
def fake_runtime_reservation_clock(request):
    # This legacy module uses a fake Runtime but real durable state storage and
    # a 2 ms wait budget. Its lifecycle tests must not benchmark the CI disk.
    # Other execution tests retain real clocks unless they explicitly opt in.
    if request.path.name == "test_rack_ai_runtime_reservations.py":
        request.getfixturevalue("reservation_poll_clock")
