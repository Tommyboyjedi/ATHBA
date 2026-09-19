"""Fail-closed local-only reasoning for the sealed post-behavior lane."""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.execution.reasoning_gateway import ReasoningRequest, ReasoningResult
from core.llm.providers.openai_provider import OpenAIProvider


@dataclass(frozen=True)
class LocalReasoningEvidence:
    invocation_id: str
    request: ReasoningRequest
    result: ReasoningResult | None = None
    error: str | None = None
    completed: bool = False


class LocalReasoningEvidenceSink(Protocol):
    def record(self, evidence: LocalReasoningEvidence) -> None: ...


class LocalOnlyPostBehaviorReasoning:
    """Accept only the configured direct local provider, with no fallback or replay."""

    def __init__(self, gateway: ProviderReasoningGateway, evidence: LocalReasoningEvidenceSink | None = None):
        self.gateway = gateway
        self.evidence = evidence
        self._require_local_provider()

    async def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self._require_local_provider()
        invocation_id = uuid4().hex
        self._record(LocalReasoningEvidence(invocation_id, request))
        try:
            result = await self.gateway.reason(request)
        except Exception as error:
            self._record(LocalReasoningEvidence(invocation_id, request, error=str(error), completed=True))
            raise
        self._record(LocalReasoningEvidence(invocation_id, request, result=result, completed=True))
        return result

    def _record(self, evidence: LocalReasoningEvidence) -> None:
        if self.evidence is not None:
            self.evidence.record(evidence)

    def _require_local_provider(self) -> None:
        if type(self.gateway) is not ProviderReasoningGateway:
            raise ValueError("post-behavior reasoning requires the direct local gateway")
        provider = self.gateway.provider
        if type(provider) is not OpenAIProvider:
            raise ValueError("post-behavior reasoning requires the direct local provider")
        endpoint = urlsplit(provider.settings.api_base)
        if endpoint.scheme not in {"http", "https"} or endpoint.username or endpoint.password:
            raise ValueError("post-behavior reasoning endpoint is not an approved local endpoint")
        if not _loopback_host(endpoint.hostname):
            raise ValueError("post-behavior reasoning cannot invoke a cloud endpoint")
        if provider.policy.max_retries != 0:
            raise ValueError("post-behavior reasoning requires zero automatic provider retries")


def _loopback_host(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return host is not None and ip_address(host).is_loopback
    except ValueError:
        return False
