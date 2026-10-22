"""One durable submission per phase and one format-only correction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from core.development.consolidation_journal import ConsolidationJournal
from core.development.consolidation_reasoning import (
    AUTHOR_PURPOSE, PROPOSAL_PURPOSE, REVIEW_PURPOSE, ConsolidationCorrection,
    ConsolidationReasoning, _object,
)
from core.execution.reasoning_gateway import ReasoningRequest

T = TypeVar("T")


class ConsolidationProtocolFailure(Exception):
    """Optional model output exhausted its single bounded format correction."""


@dataclass(frozen=True)
class ConsolidationSubmission:
    reasoning: ConsolidationReasoning
    journal: ConsolidationJournal

    async def submit(self, request: ReasoningRequest, phase: str) -> str:
        result = self.journal.recorded_call((phase, request))
        if result is None:
            result = await self.reasoning.invoke(request)
            self.journal.complete_call((phase, result))
        return result.text

    async def decode(self, submission: tuple[str, ReasoningRequest],
                     decoder: Callable[[str], T]) -> T:
        phase, request = submission
        text = await self.submit(request, phase)
        try:
            return decoder(text)
        except ValueError as error:
            protected = _protected_content(request.purpose, text)
            correction = self.reasoning.correction_request(
                request, ConsolidationCorrection(text, str(error)))
            repaired = await self.submit(correction, phase + "-format-correction")
            try:
                decoded = decoder(repaired)
                revised = _protected_content(request.purpose, repaired)
                if any(revised.get(key) != value for key, value in protected.items()):
                    raise ValueError("format correction changed previous semantic content")
                return decoded
            except ValueError as final_error:
                raise ConsolidationProtocolFailure(str(final_error)) from final_error


def _protected_content(purpose: str, text: str) -> dict[str, str]:
    """Recover semantics for comparison only; never admit a fenced response."""
    lines = text.strip().splitlines()
    fence = chr(96) * 3
    if len(lines) >= 3 and lines[0].strip() in {fence, fence + "json"} and lines[-1].strip() == fence:
        text = "\n".join(lines[1:-1])
    try:
        payload = _object(text)
        optional: tuple[str, ...]
        allowed: set[str] | None
        if purpose == AUTHOR_PURPOSE:
            required, optional, allowed = "source", (), None
        elif purpose == PROPOSAL_PURPOSE:
            required, optional, allowed = "decision", ("description",), {"YES", "NO"}
        elif purpose == REVIEW_PURPOSE:
            required, optional, allowed = "disposition", ("feedback",), {
                "approved", "repair_required", "wrong_behavior", "insufficient_evidence"}
        else:
            raise ValueError("unsupported consolidation correction purpose")
        value = payload.get(required)
        if not isinstance(value, str) or not value.strip() or (allowed is not None and value not in allowed):
            raise ValueError("previous semantic content cannot be recovered faithfully")
        protected = {required: value}
        for key in optional:
            if key in payload:
                previous = payload[key]
                if not isinstance(previous, str):
                    raise ValueError("previous semantic content cannot be recovered faithfully")
                protected[key] = previous
        return protected
    except ValueError as error:
        raise ConsolidationProtocolFailure(str(error)) from error
