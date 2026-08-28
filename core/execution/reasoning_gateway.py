"""Provider-neutral reasoning boundary for planning and architectural work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ReasoningRequest:
    """High-value reasoning request independent of any cloud vendor/model."""

    purpose: str
    prompt: str
    project_id: str
    requires_large_context: bool = False


@dataclass(frozen=True)
class ReasoningResult:
    """Normalized reasoning response used by ATHBA domain services."""

    text: str
    provider: str | None = None
    model: str | None = None


class ReasoningGateway(Protocol):
    """Port for architecture/planning reasoning; OpenRouter is the planned adapter."""

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        ...
