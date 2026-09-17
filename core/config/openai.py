from __future__ import annotations

import os
from pathlib import Path
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
        runtime_origin = os.getenv("ATHBA_RACK_AI_ORIGIN")
        credential_file = os.getenv("ATHBA_RACK_AI_CREDENTIAL_FILE")
        if not api_key and runtime_origin and credential_file:
            return cls(api_key=Path(credential_file).read_text().strip(), api_base=runtime_origin)
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        org = os.getenv("OPENAI_ORG") or os.getenv("OPENAI_PROJECT")
        api_base = os.getenv("OPENAI_API_BASE", cls.api_base)
        return cls(api_key=api_key, org=org, api_base=api_base)
