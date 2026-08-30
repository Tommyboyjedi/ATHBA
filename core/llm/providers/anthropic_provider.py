from __future__ import annotations

import json
import time
from typing import Any, Dict

import httpx
from jsonschema import ValidationError as JSONSchemaError, validate

from core.config.anthropic import AnthropicSettings
from core.llm.contracts.exceptions import ValidationError
from core.llm.contracts.provider import (
    NormalizedResult,
    ProviderRequest,
    ProviderRetryPolicy,
    build_provider_request,
)

DEFAULT_ANTHROPIC_POLICY = ProviderRetryPolicy(timeout=120.0, max_retries=3, backoff_factor=2.0)


class AnthropicProvider:
    def __init__(self, policy: ProviderRetryPolicy | None = None) -> None:
        self.settings = AnthropicSettings.from_env()
        self.policy = policy or DEFAULT_ANTHROPIC_POLICY

    def invoke(self, request_or_prompt: ProviderRequest | str, **kwargs: Any) -> NormalizedResult:
        request = build_provider_request(request_or_prompt, kwargs)
        model = request.model or self.settings.default_model
        url = f"{self.settings.api_base}/messages"
        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.response_schema:
            payload["system"] = "You must respond with valid JSON matching this schema: " + json.dumps(request.response_schema)
        for attempt in range(self.policy.max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.policy.timeout)
                if resp.status_code in {429} or 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                output_text = data.get("content", [{}])[0].get("text", "") if data.get("content") else ""
                if request.response_schema and output_text:
                    try:
                        parsed = json.loads(output_text)
                        validate(parsed, request.response_schema)
                        text_out = json.dumps(parsed)
                    except (json.JSONDecodeError, JSONSchemaError) as exc:
                        raise ValidationError(f"Schema validation failed: {exc}") from exc
                else:
                    text_out = output_text
                usage = data.get("usage", {})
                usage_dict = {"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}
                return NormalizedResult(text=text_out, usage=usage_dict, raw=data)
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                if attempt >= self.policy.max_retries:
                    raise RuntimeError(f"Anthropic API call failed after {self.policy.max_retries + 1} attempts: {error}") from error
                time.sleep(self.policy.backoff_factor ** attempt)
        raise RuntimeError("Anthropic invocation failed unexpectedly")
