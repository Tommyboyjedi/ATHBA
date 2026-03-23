from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AnthropicSettings:
    """Configuration for the Anthropic/Claude provider."""

    api_key: str
    api_base: str = "https://api.anthropic.com/v1"
    default_model: str = "claude-sonnet-4.5-20250514"

    @classmethod
    def from_env(cls) -> "AnthropicSettings":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        api_base = os.getenv("ANTHROPIC_API_BASE", cls.api_base)
        default_model = os.getenv("ANTHROPIC_DEFAULT_MODEL", cls.default_model)
        return cls(api_key=api_key, api_base=api_base, default_model=default_model)
