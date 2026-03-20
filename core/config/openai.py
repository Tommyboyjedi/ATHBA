from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class OpenAISettings:
    """Configuration for the OpenAI provider."""

    api_key: str
    org: str | None = None
    api_base: str = "https://api.openai.com/v1"

    @classmethod
    def from_env(cls) -> "OpenAISettings":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        org = os.getenv("OPENAI_ORG") or os.getenv("OPENAI_PROJECT")
        api_base = os.getenv("OPENAI_API_BASE", cls.api_base)
        return cls(api_key=api_key, org=org, api_base=api_base)
