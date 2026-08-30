from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol


@dataclass
class NormalizedResult:
    text: str
    usage: Dict[str, int]
    raw: Dict[str, Any]


@dataclass(frozen=True)
class ProviderRequest:
    prompt: str
    model: str | None
    temperature: float = 0.0
    max_tokens: int = 16
    response_schema: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ProviderRetryPolicy:
    timeout: float
    max_retries: int
    backoff_factor: float


def build_provider_request(request_or_prompt: ProviderRequest | str, options: Dict[str, Any]) -> ProviderRequest:
    if isinstance(request_or_prompt, ProviderRequest):
        return request_or_prompt
    return ProviderRequest(
        prompt=request_or_prompt,
        model=options.get("model"),
        temperature=float(options.get("temperature", 0.0)),
        max_tokens=int(options.get("max_tokens", 16)),
        response_schema=options.get("response_schema"),
    )


class Provider(Protocol):
    def invoke(self, request_or_prompt: ProviderRequest | str, **kwargs: Any) -> NormalizedResult:
        ...
