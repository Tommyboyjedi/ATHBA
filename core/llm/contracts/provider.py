from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class NormalizedResult:
    text: str
    usage: dict[str, int]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ProviderRequest:
    prompt: str
    model: str | None
    temperature: float = 0.0
    max_tokens: int = 16
    response_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderRetryPolicy:
    timeout: float
    max_retries: int
    backoff_factor: float


class Provider(Protocol):
    def invoke(self, request: ProviderRequest) -> NormalizedResult:
        ...
