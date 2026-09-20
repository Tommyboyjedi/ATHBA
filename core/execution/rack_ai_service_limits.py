"""RackAI-published service execution limits."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.execution.rack_ai_runtime import RackAiResourceWait


@dataclass(frozen=True)
class RackAiServiceLimits:
    max_input_tokens: int
    max_output_tokens: int

    @classmethod
    def from_reserved_service(
        cls, service: str, member: Mapping[str, object]
    ) -> "RackAiServiceLimits":
        return cls(
            _required_positive_int(member, service, "max_input_tokens"),
            _required_positive_int(member, service, "max_output_tokens"),
        )


def _required_positive_int(
    member: Mapping[str, object], service: str, field: str
) -> int:
    value = member.get(field)
    nested = member.get("limits")
    if value is None and isinstance(nested, Mapping):
        value = nested.get(field)
    if isinstance(value, bool) or type(value) is not int or value <= 0:
        raise RackAiResourceWait(f"RackAI {service} did not publish {field}")
    return value
