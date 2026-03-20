from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import httpx
from jsonschema import ValidationError as JSONSchemaError, validate

from core.config.openai import OpenAISettings
from core.llm.contracts.exceptions import ValidationError
from core.llm.contracts.provider import NormalizedResult, Provider


class OpenAIProvider(Provider):
    """LLM provider that calls OpenAI's Responses API."""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        self.settings = OpenAISettings.from_env()
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def invoke(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 16,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> NormalizedResult:
        url = f"{self.settings.api_base}/responses"
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
        }
        if self.settings.org:
            headers["OpenAI-Organization"] = self.settings.org

        payload: Dict[str, Any] = {
            "model": model,
            "input": prompt,
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "pm_intent", "schema": response_schema},
            }

        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                if resp.status_code in {429} or 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError("retryable", request=resp.request, response=resp)
                resp.raise_for_status()
                data = resp.json()
                output_text = (
                    data.get("output", [{}])[0]
                    .get("content", [{}])[0]
                    .get("text", "")
                )
                if response_schema:
                    parsed = json.loads(output_text)
                    try:
                        validate(parsed, response_schema)
                    except JSONSchemaError as exc:
                        raise ValidationError(str(exc)) from exc
                    text_out = json.dumps(parsed)
                else:
                    text_out = output_text
                usage = data.get("usage", {})
                usage_dict = {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                }
                return NormalizedResult(text=text_out, usage=usage_dict, raw=data)
            except (httpx.RequestError, httpx.HTTPStatusError):
                if attempt >= self.max_retries:
                    raise
                sleep = self.backoff_factor ** attempt
                time.sleep(sleep)
                continue
