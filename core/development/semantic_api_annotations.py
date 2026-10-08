"""Deterministic API interaction annotations for Tester context."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SemanticInteraction(str, Enum):
    INVOKE = "invoke"
    READ = "read"
    CONSTRUCT = "construct"
    WRITE = "write"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ApiExpressionDescriptionRequest:
    source_expression: str

    def __post_init__(self) -> None:
        if not self.source_expression.strip():
            raise ValueError("source expression must be non-empty")


@dataclass(frozen=True)
class SemanticApiAnnotation:
    symbol: str | None
    interaction: str
    source_expression: str
    result: str | None = None
    receiver_owner: str | None = None
    argument_count: int | None = None

    def __post_init__(self) -> None:
        if self.symbol is not None and not self.symbol.strip():
            raise ValueError("semantic annotation symbol must be non-empty when supplied")
        if not self.source_expression.strip():
            raise ValueError("semantic annotation source expression must be non-empty")
        if self.receiver_owner is not None and not self.receiver_owner.strip():
            raise ValueError("receiver owner must be non-empty")
        if self.argument_count is not None and self.argument_count < 0:
            raise ValueError("argument count must be non-negative")
        object.__setattr__(self, "interaction", SemanticInteraction(self.interaction).value)
        if self.result is not None and not self.result.strip():
            raise ValueError("semantic annotation result must be non-empty when supplied")

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "symbol": self.symbol,
            "interaction": self.interaction,
            "source_expression": self.source_expression,
            "result": self.result,
        }
        if self.receiver_owner is not None:
            result["receiver_owner"] = self.receiver_owner
        if self.argument_count is not None:
            result["argument_count"] = self.argument_count
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SemanticApiAnnotation":
        return cls(
            symbol=None if value.get("symbol") is None else str(value["symbol"]),
            interaction=str(value["interaction"]),
            source_expression=str(value["source_expression"]),
            result=None if value.get("result") is None else str(value["result"]),
            receiver_owner=None if value.get("receiver_owner") is None else str(value["receiver_owner"]),
            argument_count=None if value.get("argument_count") is None else int(value["argument_count"]),
        )
