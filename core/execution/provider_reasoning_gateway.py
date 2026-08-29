"""Provider-backed ReasoningGateway adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest, ReasoningResult
from core.llm.contracts.provider import Provider


@dataclass(frozen=True)
class ProviderReasoningGateway(ReasoningGateway):
    provider: Provider
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        result = await asyncio.to_thread(
            self.provider.invoke,
            request.prompt,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        raw = dict(result.raw)
        provider_name = raw.get("provider")
        if provider_name is not None:
            provider_name = str(provider_name)
        model_name = raw.get("model")
        if model_name is not None:
            model_name = str(model_name)
        return ReasoningResult(text=result.text, provider=provider_name, model=model_name or self.model)
