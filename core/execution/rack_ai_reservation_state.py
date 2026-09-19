"""Reservation identity embedded in existing durable ATHBA run records."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RackAiReservationState:
    work_id: str
    acquisition_id: str
    services: tuple[str, ...]
    priority: str
    ttl_seconds: int
    reservation_id: str | None = None
    release_requested: bool = False
    released: bool = False
    waiting_service: str | None = None
    pending_workspace: str | None = None
    pending_inference: str | None = None
    ready_observed: bool = False
    workspace_generations: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.priority not in {"low", "medium"}:
            raise ValueError("ATHBA reservation priority must not exceed medium")
        if not self.services or len(set(self.services)) != len(self.services):
            raise ValueError("reservation requires distinct campaign services")
        for key, value in self.workspace_generations.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(value, int) or value < 0:
                raise ValueError("workspace execution generations must be non-negative by submission")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> RackAiReservationState:
        generations = value.get("workspace_generations", {})
        if not isinstance(generations, dict):
            raise ValueError("workspace execution generations must be a mapping")
        return cls(**{
            **value,
            "services": tuple(value["services"]),
            "ready_observed": bool(value.get("ready_observed", False)),
            "workspace_generations": {str(key): int(item) for key, item in generations.items()},
        })


class ReservationStateRepository(Protocol):
    def load_reservation(self, identity: str) -> RackAiReservationState | None: ...
    def save_reservation(self, identity: str, state: RackAiReservationState) -> None: ...


@dataclass(frozen=True)
class ReservationBinding:
    repository: ReservationStateRepository
    identity: str

    def load(self) -> RackAiReservationState | None:
        return self.repository.load_reservation(self.identity)

    def save(self, state: RackAiReservationState) -> None:
        self.repository.save_reservation(self.identity, state)


class ReservationRecord:
    """Update only the RackAI field of an existing ATHBA state document."""
    def __init__(self, path):
        self.path = path

    def load(self) -> RackAiReservationState | None:
        from core.atomic_json_file import read_json_file
        value = read_json_file(self.path).get("rack_ai")
        return None if value is None else RackAiReservationState.from_dict(value)

    def save(self, state: RackAiReservationState) -> None:
        from core.atomic_json_file import read_json_file, write_json_atomically
        value = read_json_file(self.path)
        value["rack_ai"] = state.to_dict()
        write_json_atomically(self.path, value)

    def preserve(self, value: dict) -> dict:
        if self.path.exists():
            state = self.load()
            if state is not None:
                value = {**value, "rack_ai": state.to_dict()}
        return value
