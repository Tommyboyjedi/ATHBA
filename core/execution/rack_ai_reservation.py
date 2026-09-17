"""One campaign's client-side use of RackAI's existing reservation lifecycle."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from threading import RLock
import time
from uuid import uuid4

from core.execution.rack_ai_reservation_state import RackAiReservationState, ReservationBinding
from core.execution.rack_ai_runtime import RackAiResourceWait, RackAiRuntimeClient, RackAiRuntimeError

TERMINAL_RESERVATIONS = frozenset({"released", "cancelled", "expired"})
WAITING_SERVICES = frozenset({"preparing", "held", "draining", "unavailable"})


def runtime_identity(value: str) -> str:
    return "athba-" + sha256(value.encode()).hexdigest()


class RackAiReservation:
    def __init__(self, client: RackAiRuntimeClient, services: tuple[str, ...]):
        self.client = client
        self.services = services
        self.binding: ReservationBinding | None = None
        self.lock = RLock()
        self.call_sequence = 0
        self.transition_identity = ""
        self.closed = False

    def bind(self, binding: ReservationBinding) -> None:
        if self.binding is not None and self.binding != binding:
            raise ValueError("RackAI adapter is already bound to another campaign")
        first_binding = self.binding is None
        self.binding = binding
        state = binding.load()
        try:
            if (first_binding or self.closed) and state is not None and state.reservation_id is not None:
                view = self.client.operation({"operation": "inspect_reservation", "reservation_id": state.reservation_id})
                if state.release_requested and view["state"] in TERMINAL_RESERVATIONS:
                    state = replace(state, released=True)
                    binding.save(state)
            if state is not None and state.release_requested and not state.released:
                self.finish()
        except RackAiRuntimeError as error:
            raise RackAiResourceWait(f"reservation resume: {error.code}") from error
        self.closed = False

    def transition(self, identity: str) -> None:
        self.transition_identity = identity
        self.call_sequence = 0

    def call_identity(self, payload: str) -> str:
        self.call_sequence += 1
        return runtime_identity(f"{self._binding().identity}:{self.transition_identity}:{self.call_sequence}:{payload}")

    def current(self) -> dict:
        with self.lock:
            if self.closed:
                raise RackAiResourceWait("campaign resource access is closed")
            binding = self._binding()
            state = binding.load()
            if state is not None and state.services != self.services:
                raise RackAiResourceWait("persisted campaign service requirements changed")
            if state is not None and state.reservation_id is not None:
                view = self.client.operation({"operation": "inspect_reservation", "reservation_id": state.reservation_id})
                if view["state"] not in TERMINAL_RESERVATIONS:
                    if state.release_requested:
                        raise RackAiResourceWait("reservation release is still pending")
                    return view
            if state is None or state.reservation_id is not None:
                state = RackAiReservationState(runtime_identity(binding.identity), uuid4().hex,
                                              self.services, state.priority if state is not None else "low",
                                              self.client.configuration.ttl_seconds)
                binding.save(state)
            return self._reserve(state)

    def _reserve(self, state: RackAiReservationState) -> dict:
        result = self.client.operation({"operation": "reserve", "request": {
            "work_id": state.work_id, "acquisition_id": state.acquisition_id,
            "services": list(state.services), "priority": state.priority, "ttl_seconds": state.ttl_seconds,
        }})
        reservation_id = result.get("id")
        if not isinstance(reservation_id, str) or not reservation_id:
            raise RackAiRuntimeError("missing_reservation_identity")
        self._binding().save(replace(state, reservation_id=reservation_id))
        # Reserve replay is the durable original receipt, never a status/refresh query.
        return self.client.operation({"operation": "inspect_reservation", "reservation_id": reservation_id})

    def mark_wait(self, service: str | None) -> None:
        with self.lock:
            binding = self._binding()
            state = binding.load()
            if state is not None and state.waiting_service != service:
                binding.save(replace(state, waiting_service=service))

    def mark_workspace(self, identity: str | None) -> None:
        with self.lock:
            binding = self._binding()
            state = binding.load()
            if state is not None:
                binding.save(replace(state, pending_workspace=identity))

    def ready(self, service: str) -> dict:
        return ReservationAccessWait(self).ready(service)

    def finish(self) -> None:
        self.closed = True
        with self.lock:
            binding = self._binding()
            state = binding.load()
            if state is None or state.released:
                return
            binding.save(replace(state, release_requested=True))
            if state.reservation_id is None:
                self._reserve(replace(state, release_requested=True))
                state = binding.load()
            assert state is not None
            self.client.operation({"operation": "release_reservation", "reservation_id": state.reservation_id})
            binding.save(replace(state, release_requested=True, released=True))

    def _binding(self) -> ReservationBinding:
        if self.binding is None:
            raise RackAiResourceWait("RackAI requires a durable campaign binding before execution")
        return self.binding


class ReservationAccessWait:
    def __init__(self, reservation: RackAiReservation):
        self.reservation = reservation

    def ready(self, service: str) -> dict:
        reservation = self.reservation
        if service not in reservation.services:
            raise RackAiResourceWait("service was not requested by this campaign")
        config = reservation.client.configuration
        deadline = time.monotonic() + config.resource_wait_seconds
        refresh_at = 0.0
        reason = "runtime_unavailable"
        while True:
            try:
                view = reservation.current()
                member = view["services"][service]
                reason = member["state"]
                if reason == "ready":
                    reservation.mark_wait(None)
                    return {**member, "reservation_id": view["id"]}
                reservation.mark_wait(service)
                if reason not in WAITING_SERVICES:
                    raise RackAiResourceWait(f"RackAI {service}: {reason}")
                if reason == "unavailable" and time.monotonic() >= refresh_at:
                    reservation.client.operation({"operation": "refresh_reservation", "reservation_id": view["id"]})
                    refresh_at = time.monotonic() + config.refresh_seconds
            except RackAiRuntimeError as error:
                reason = error.code
                if error.status not in {0, 429, 502, 503, 504}:
                    raise RackAiResourceWait(f"RackAI {service}: {reason}") from error
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RackAiResourceWait(f"RackAI {service}: {reason}; resource wait bound reached")
            time.sleep(min(config.poll_seconds, remaining))
