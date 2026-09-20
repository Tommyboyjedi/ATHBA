"""One campaign's client-side use of RackAI's existing reservation lifecycle."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from threading import RLock
import time
from uuid import uuid4

from core.execution.rack_ai_reservation_state import RackAiReservationState, ReservationBinding
from core.execution.rack_ai_runtime import RackAiResourceWait, RackAiRuntimeClient, RackAiRuntimeError
from core.execution.rack_ai_service_limits import RackAiServiceLimits

TERMINAL_RESERVATIONS = frozenset({"released", "cancelled", "expired", "preempted"})
WAITING_RESERVATIONS = frozenset({"preparing", "partial", "preempting", "releasing", "recovery_required"})
WAITING_SERVICES = frozenset({"preparing", "unavailable", "preempting", "releasing", "recovery_required"})
UNOWNED_RESERVATIONS = frozenset({"unavailable"})


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
                try:
                    view = self.client.operation({"operation": "inspect_reservation", "reservation_id": state.reservation_id})
                except RackAiRuntimeError as error:
                    if (error.code == "not_found" and state.reservation_id.startswith("unavailable-")
                            and not state.pending_workspace and not state.pending_inference):
                        state = replace(state, reservation_id=None, ready_observed=False, service_limits={})
                        binding.save(state)
                    else:
                        raise
                else:
                    state = self._remember_ready(state, view)
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
                try:
                    view = self.client.operation({"operation": "inspect_reservation", "reservation_id": state.reservation_id})
                except RackAiRuntimeError as error:
                    if (error.code == "not_found" and state.reservation_id.startswith("unavailable-")
                            and not state.pending_workspace and not state.pending_inference):
                        state = replace(state, reservation_id=None, ready_observed=False, service_limits={})
                        binding.save(state)
                    else:
                        raise RackAiResourceWait(f"reservation inspect: {error.code}") from error
                else:
                    state = self._remember_ready(state, view)
                    if view["state"] not in TERMINAL_RESERVATIONS:
                        if state.release_requested:
                            raise RackAiResourceWait("reservation release is still pending")
                        return view
                    if state.pending_workspace or state.pending_inference:
                        raise RackAiResourceWait("terminal reservation has unresolved work")
            if state is None or state.reservation_id is not None:
                state = RackAiReservationState(
                    runtime_identity(binding.identity), uuid4().hex, self.services, "low",
                    self.client.configuration.ttl_seconds,
                    workspace_generations={} if state is None else dict(state.workspace_generations),
                )
                binding.save(state)
            return self._reserve(state)

    def _remember_ready(self, state: RackAiReservationState, view: dict) -> RackAiReservationState:
        return _remember_ready_state(self._binding(), state, view)

    def workspace_execution_identity(self, submission_id: str) -> str:
        return _workspace_execution_identity(self._binding(), submission_id)

    def advance_workspace_generation(self, submission_id: str) -> None:
        with self.lock:
            _advance_workspace_generation(self._binding(), submission_id)

    def _reserve(self, state: RackAiReservationState) -> dict:
        return _reserve_state(self.client, self._binding(), state)

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

    def service_limits(self, service: str) -> RackAiServiceLimits:
        with self.lock:
            if service not in self.services:
                raise RackAiResourceWait("service was not requested by this campaign")
            state = self._binding().load()
            if state is None:
                raise RackAiResourceWait(f"RackAI {service} did not publish max_input_tokens")
            member = state.service_limits.get(service)
            if member is None:
                raise RackAiResourceWait(f"RackAI {service} did not publish max_input_tokens")
            return RackAiServiceLimits.from_reserved_service(service, member)

    def finish(self) -> None:
        self.closed = True
        with self.lock:
            _finish_reservation(self.client, self._binding())

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
        reason = "runtime_unavailable"
        while True:
            delay = config.poll_seconds
            try:
                view = reservation.current()
                state = reservation._binding().load()
                if state is not None and not state.ready_observed:
                    if _reservation_ready(view, reservation.services):
                        reservation._remember_ready(state, view)
                    else:
                        reason = _blocking_reason(view, service, reservation.services)
                        reservation.mark_wait(service)
                        if reason in TERMINAL_RESERVATIONS:
                            self._replace_terminal_member()
                        elif reason not in WAITING_RESERVATIONS and reason not in UNOWNED_RESERVATIONS:
                            raise RackAiResourceWait(f"RackAI reservation: {reason}")
                        raise _StillWaiting(reason, _retry_after(view, service))
                member = view["services"][service]
                reason = member["state"]
                if reason == "ready":
                    reservation.mark_wait(None)
                    return {**member, "reservation_id": view["id"]}
                reservation.mark_wait(service)
                if reason in TERMINAL_RESERVATIONS:
                    self._replace_terminal_member()
                elif reason not in WAITING_SERVICES:
                    raise RackAiResourceWait(f"RackAI {service}: {reason}")
                raise _StillWaiting(reason, _retry_after(view, service))
            except _StillWaiting as waiting:
                reason = waiting.reason
                if waiting.retry_after is not None:
                    delay = max(config.poll_seconds, waiting.retry_after)
            except RackAiRuntimeError as error:
                reason = error.code
                if error.status not in {0, 429, 502, 503, 504}:
                    raise RackAiResourceWait(f"RackAI {service}: {reason}") from error
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RackAiResourceWait(f"RackAI {service}: {reason}; resource wait bound reached")
            time.sleep(min(delay, remaining))

    def _replace_terminal_member(self) -> None:
        reservation = self.reservation
        with reservation.lock:
            state = reservation._binding().load()
            if state is None or state.pending_workspace or state.pending_inference:
                raise RackAiResourceWait("terminal member has unresolved work; reconcile before replacement")
            reservation.finish()
            reservation.closed = False


def _finish_reservation(client: RackAiRuntimeClient, binding: ReservationBinding) -> None:
    state = binding.load()
    if state is None or state.released:
        return
    binding.save(replace(state, release_requested=True))
    if state.reservation_id is None:
        binding.save(replace(state, release_requested=True, released=True))
        return
    client.operation({"operation": "release_reservation", "reservation_id": state.reservation_id})
    binding.save(replace(state, release_requested=True, released=True))


def _remember_ready_state(binding: ReservationBinding, state: RackAiReservationState, view: dict) -> RackAiReservationState:
    if _reservation_ready(view, state.services):
        service_limits = _ready_service_limits(view, state.services)
        updated = replace(state, ready_observed=True, service_limits=service_limits)
        if updated != state:
            binding.save(updated)
        return updated
    return state


def _ready_service_limits(view: dict, services: tuple[str, ...]) -> dict[str, dict[str, int]]:
    members = view.get("services")
    if not isinstance(members, dict):
        raise RackAiResourceWait("RackAI reservation services are malformed")
    limits: dict[str, dict[str, int]] = {}
    for service in services:
        member = members.get(service)
        if not isinstance(member, dict):
            raise RackAiResourceWait(f"RackAI {service} service record is malformed")
        published = RackAiServiceLimits.from_reserved_service(service, member)
        limits[service] = {
            "max_input_tokens": published.max_input_tokens,
            "max_output_tokens": published.max_output_tokens,
        }
    return limits


def _workspace_execution_identity(binding: ReservationBinding, submission_id: str) -> str:
    state = binding.load()
    generation = 0 if state is None else state.workspace_generations.get(submission_id, 0)
    suffix = "" if generation == 0 else f":execution-{generation}"
    return runtime_identity(f"{binding.identity}:{submission_id}{suffix}")


def _advance_workspace_generation(binding: ReservationBinding, submission_id: str) -> None:
    state = binding.load()
    if state is None:
        raise RackAiResourceWait("workspace preemption has no durable reservation")
    if state.pending_workspace not in {None, submission_id}:
        raise RackAiResourceWait("another workspace execution is unresolved")
    generations = dict(state.workspace_generations)
    generations[submission_id] = generations.get(submission_id, 0) + 1
    binding.save(replace(state, pending_workspace=None, workspace_generations=generations))


def _reserve_state(client: RackAiRuntimeClient, binding: ReservationBinding, state: RackAiReservationState) -> dict:
    state = replace(
        state, priority="low", reservation_id=None, ready_observed=False,
        service_limits={}, release_requested=False, released=False,
    )
    result = client.operation({"operation": "reserve", "request": {
        "work_id": state.work_id, "acquisition_id": state.acquisition_id,
        "services": list(state.services), "priority": state.priority, "ttl_seconds": state.ttl_seconds,
    }})
    if result.get("state") in UNOWNED_RESERVATIONS:
        binding.save(state)
        return result
    reservation_id = result.get("id")
    if not isinstance(reservation_id, str) or not reservation_id:
        raise RackAiRuntimeError("missing_reservation_identity")
    state = replace(state, reservation_id=reservation_id,
                    ready_observed=False, service_limits={})
    binding.save(state)
    # Reserve replay is the durable original receipt, never a status/refresh query.
    view = client.operation({"operation": "inspect_reservation", "reservation_id": reservation_id})
    _remember_ready_state(binding, state, view)
    return view


class _StillWaiting(Exception):
    def __init__(self, reason: str, retry_after: float | None = None):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


def _reservation_ready(view: dict, services: tuple[str, ...]) -> bool:
    members = view.get("services")
    return (view.get("state") == "ready" and isinstance(members, dict)
            and all(isinstance(members.get(service), dict)
                    and members[service].get("state") == "ready" for service in services))


def _blocking_reason(view: dict, service: str, services: tuple[str, ...]) -> str:
    members = view.get("services")
    if isinstance(members, dict):
        preferred = members.get(service)
        if isinstance(preferred, dict) and preferred.get("state") != "ready":
            return str(preferred.get("state", view.get("state", "runtime_unavailable")))
        for name in services:
            member = members.get(name)
            if isinstance(member, dict) and member.get("state") != "ready":
                return str(member.get("state", view.get("state", "runtime_unavailable")))
    return str(view.get("state", "runtime_unavailable"))


def _retry_after(view: dict, service: str) -> float | None:
    candidates = [view.get("retry_after")]
    member = view.get("services", {}).get(service) if isinstance(view.get("services"), dict) else None
    if isinstance(member, dict):
        candidates.append(member.get("retry_after"))
    for value in candidates:
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return None
