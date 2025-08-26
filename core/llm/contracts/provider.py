from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class NormalizedResult:
    """Standardized response from an LLM provider."""

    text: str
    usage: Dict[str, int]
    raw: Dict[str, Any]


class Provider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def invoke(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 16,
        response_schema: Optional[Dict[str, Any]] = None,
    ) -> NormalizedResult:
        """Invoke the provider with a prompt and generation options."""
        raise NotImplementedError
