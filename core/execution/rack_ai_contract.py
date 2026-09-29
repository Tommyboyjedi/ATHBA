"""Public ATHBA RackAI boundary helpers."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from core.execution.rack_ai_request import RepositoryBinding, to_rack_ai_request

FORBIDDEN_RESOURCE_SELECTION_KEYS = {
    "backend",
    "backends",
    "device",
    "device_id",
    "endpoint",
    "endpoint_id",
    "endpoint_url",
    "gpu",
    "gpu_id",
    "gpu_ids",
    "model",
    "model_id",
    "model_ids",
    "port",
    "resource_ids",
    "selected_worker",
    "selected_worker_id",
    "worker",
    "worker_id",
    "worker_ids",
}


@dataclass(frozen=True)
class _ResourceScanState:
    forbidden_keys: set[str]
    matches: list[str]
    path: str = ""


class _ForbiddenResourceSelectionScanner:
    def scan(self, payload: Any, forbidden_keys: set[str]) -> list[str]:
        matches: list[str] = []
        self._walk(payload, _ResourceScanState(forbidden_keys, matches))
        return matches

    def _walk(self, payload: Any, state: _ResourceScanState) -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                key_name = str(key)
                child_path = f"{state.path}.{key_name}" if state.path else key_name
                if key_name.lower() in state.forbidden_keys:
                    state.matches.append(child_path)
                self._walk(value, _ResourceScanState(state.forbidden_keys, state.matches, child_path))
            return
        if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
            for index, value in enumerate(payload):
                child_path = f"{state.path}[{index}]"
                self._walk(value, _ResourceScanState(state.forbidden_keys, state.matches, child_path))


def find_forbidden_resource_selection_keys(
    payload: Any, forbidden_keys: set[str] | None = None
) -> list[str]:
    keys = FORBIDDEN_RESOURCE_SELECTION_KEYS if forbidden_keys is None else forbidden_keys
    return _ForbiddenResourceSelectionScanner().scan(payload, keys)


__all__ = [
    "FORBIDDEN_RESOURCE_SELECTION_KEYS",
    "RepositoryBinding",
    "find_forbidden_resource_selection_keys",
    "to_rack_ai_request",
]
