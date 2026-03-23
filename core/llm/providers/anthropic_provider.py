from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import httpx
from jsonschema import ValidationError as JSONSchemaError, validate

from core.config.anthropic import AnthropicSettings
from core.llm.contracts.exceptions import ValidationError
from core.llm.contracts.provider import NormalizedResult, Provider


class AnthropicProvider(Provider):
    """LLM provider that calls Anthropic's Claude API."""

    def __init__(
        self,
        *,
        timeout: float = 120.0,  # Longer timeout for complex analysis
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> None:
        self.settings = AnthropicSettings.from_env()
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def invoke(
        self,
        prompt: str,
        *,
        model: str = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> NormalizedResult:
        """
        Invoke Claude API with the given prompt.
        
        Args:
            prompt: The prompt to send to Claude
            model: Model to use (defaults to claude-sonnet-4.5)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            response_schema: Optional JSON schema for structured output
        
        Returns:
            NormalizedResult with response text and usage statistics
        """
        if model is None:
            model = self.settings.default_model
            
        url = f"{self.settings.api_base}/messages"
        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        # If response schema is provided, add it as a system message
        if response_schema:
            payload["system"] = (
                "You must respond with valid JSON matching this schema: "
                f"{json.dumps(response_schema)}"
            )

        for attempt in range(self.max_retries + 1):
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=self.timeout)
                
                # Retry on rate limits or server errors
                if resp.status_code in {429} or 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(
                        "retryable", 
                        request=resp.request, 
                        response=resp
                    )
                
                resp.raise_for_status()
                data = resp.json()
                
                # Extract text from Claude's response format
                output_text = ""
                if "content" in data and len(data["content"]) > 0:
                    output_text = data["content"][0].get("text", "")
                
                # Validate against schema if provided
                if response_schema and output_text:
                    try:
                        parsed = json.loads(output_text)
                        validate(parsed, response_schema)
                        text_out = json.dumps(parsed)
                    except (json.JSONDecodeError, JSONSchemaError) as exc:
                        raise ValidationError(f"Schema validation failed: {exc}") from exc
                else:
                    text_out = output_text
                
                # Extract usage information
                usage = data.get("usage", {})
                usage_dict = {
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                }
                
                return NormalizedResult(text=text_out, usage=usage_dict, raw=data)
                
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt >= self.max_retries:
                    # On final failure, raise with context
                    raise RuntimeError(
                        f"Anthropic API call failed after {self.max_retries + 1} attempts: {e}"
                    ) from e
                
                # Exponential backoff
                sleep = self.backoff_factor ** attempt
                time.sleep(sleep)
                continue
