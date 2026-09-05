"""Strict model-output contract and auditable reconciliation failures."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import json
from typing import Any


class ReconciliationFailureKind(str, Enum):
    MALFORMED = "reconciliation_malformed_output"
    SCHEMA = "reconciliation_invalid_response"
    SEMANTIC = "reconciliation_invalid_answer"
    PROVIDER = "reconciliation_provider_failure"


@dataclass(frozen=True)
class ReconciliationAttempt:
    submission: int
    format_repair: bool
    outcome: str
    response_sha256: str | None = None


@dataclass(frozen=True)
class ReconciliationFailure(Exception):
    kind: ReconciliationFailureKind
    diagnostic: str
    checklist_ref: str = ""
    accepted_test_names: tuple[str, ...] = ()
    attempts: tuple[ReconciliationAttempt, ...] = ()
    completed_results: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "kind": self.kind.value}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReconciliationFailure:
        return cls(ReconciliationFailureKind(payload["kind"]), payload["diagnostic"],
                   payload["checklist_ref"], tuple(payload["accepted_test_names"]),
                   tuple(ReconciliationAttempt(**item) for item in payload["attempts"]),
                   tuple(payload.get("completed_results", ())))


@dataclass(frozen=True)
class ReconciliationResponse:
    answer: str
    selected_test_names: tuple[str, ...]
    rationale: str

    @staticmethod
    def schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "enum": ["YES", "NO"]},
                "selected_test_names": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
            "required": ["answer", "selected_test_names", "rationale"],
            "additionalProperties": False,
        }

    @classmethod
    def decode(cls, text: str) -> ReconciliationResponse:
        try:
            payload = json.loads(_normalise_json_object(text))
        except json.JSONDecodeError as error:
            raise ReconciliationFailure(
                ReconciliationFailureKind.MALFORMED, "response was not valid JSON"
            ) from error
        if not isinstance(payload, dict) or set(payload) != set(cls.schema()["required"]):
            raise ReconciliationFailure(
                ReconciliationFailureKind.SCHEMA, "response requires exactly answer, selected_test_names and rationale"
            )
        answer, selected, rationale = payload['answer'], payload['selected_test_names'], payload['rationale']
        if not isinstance(selected, list) or any(not isinstance(name, str) for name in selected):
            raise ReconciliationFailure(ReconciliationFailureKind.SCHEMA, "selected_test_names must be an array of strings")
        if not isinstance(rationale, str):
            raise ReconciliationFailure(ReconciliationFailureKind.SCHEMA, "rationale must be a string")
        if not isinstance(answer, str) or answer not in {"YES", "NO"}:
            raise ReconciliationFailure(ReconciliationFailureKind.SEMANTIC, "answer must be YES or NO")
        if answer == "NO" and selected:
            raise ReconciliationFailure(ReconciliationFailureKind.SEMANTIC, "NO cannot claim accepted evidence")
        return cls(answer, tuple(selected), rationale)


def _normalise_json_object(text: str) -> str:
    source = text.strip()
    lines = source.splitlines()
    if len(lines) < 3 or lines[0] not in {"```", "```json"} or lines[-1] != "```":
        return source
    return "\n".join(lines[1:-1])
