"""Provider-backed ReasoningGateway adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.llm.contracts.provider import Provider, ProviderRequest


@dataclass(frozen=True)
class ProviderReasoningGateway:
    provider: Provider
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        provider_request = ProviderRequest(
            prompt=request.prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        result = await asyncio.to_thread(self.provider.invoke, provider_request)
        raw = dict(result.raw)
        provider_name = raw.get("provider")
        if provider_name is not None:
            provider_name = str(provider_name)
        model_name = raw.get("model")
        if model_name is not None:
            model_name = str(model_name)
        return ReasoningResult(text=result.text, provider=provider_name, model=model_name or self.model)
