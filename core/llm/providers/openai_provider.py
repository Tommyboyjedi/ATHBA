from __future__ import annotations

import json
import time
from typing import Any, Dict

import httpx
from jsonschema import ValidationError as JSONSchemaError, validate

from core.config.openai import OpenAISettings
from core.llm.contracts.exceptions import ValidationError
from core.llm.contracts.provider import (
    NormalizedResult,
    ProviderRequest,
    ProviderRetryPolicy,
    build_provider_request,
)

DEFAULT_OPENAI_POLICY = ProviderRetryPolicy(timeout=30.0, max_retries=3, backoff_factor=2.0)


def _policy_with_max_retries(policy: ProviderRetryPolicy | None, max_retries: int | None) -> ProviderRetryPolicy:
    base = policy or DEFAULT_OPENAI_POLICY
    if max_retries is None:
        return base
    return ProviderRetryPolicy(timeout=base.timeout, max_retries=max_retries, backoff_factor=base.backoff_factor)


class OpenAIProvider:
    def __init__(self, policy: ProviderRetryPolicy | None = None, *, max_retries: int | None = None) -> None:
        self.settings = OpenAISettings.from_env()
        self.policy = _policy_with_max_retries(policy, max_retries)

    def invoke(self, request_or_prompt: ProviderRequest | str, **kwargs: Any) -> NormalizedResult:
        request = build_provider_request(request_or_prompt, kwargs)
        url = f"{self.settings.api_base}/responses"
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        if self.settings.org:
            headers["OpenAI-Organization"] = self.settings.org
        payload: Dict[str, Any] = {
            "model": request.model,
            "input": request.prompt,
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }
        if request.response_schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "pm_intent", "schema": request.response_schema}}
        for attempt in range(self.policy.max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.policy.timeout)
                if resp.status_code in {429} or 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                output_text = data.get("output", [{}])[0].get("content", [{}])[0].get("text", "")
                if request.response_schema:
                    parsed = json.loads(output_text)
                    try:
                        validate(parsed, request.response_schema)
                    except JSONSchemaError as exc:
                        raise ValidationError(str(exc)) from exc
                    text_out = json.dumps(parsed)
                else:
                    text_out = output_text
                usage = data.get("usage", {})
                usage_dict = {"input_tokens": usage.get("input_tokens", 0), "output_tokens": usage.get("output_tokens", 0)}
                return NormalizedResult(text=text_out, usage=usage_dict, raw=data)
            except (httpx.RequestError, httpx.HTTPStatusError):
                if attempt >= self.policy.max_retries:
                    raise
                time.sleep(self.policy.backoff_factor ** attempt)
        raise RuntimeError("OpenAI invocation failed unexpectedly")
