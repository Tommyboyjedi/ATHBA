"""One durable submission per phase and one shared bounded correction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from core.development.consolidation_coverage_correction import coverage_correction_request, protect_coverage
from core.development.consolidation_journal import ConsolidationJournal
from core.development.consolidation_reasoning import (
    AUTHOR_PURPOSE, PROPOSAL_PURPOSE, REVIEW_PURPOSE, ConsolidationCorrection,
    ConsolidationContextLimit, ConsolidationCoverageMissing, ConsolidationReasoning, ConsolidationReplacement, _object,
)
from core.development.scenario_intent_review import _normalise_json_object
from core.execution.provider_reasoning_gateway import wait_for_reasoning
from core.execution.reasoning_gateway import ReasoningRequest

T = TypeVar("T")


class ConsolidationProtocolFailure(Exception):
    """Optional model output exhausted its single bounded format correction."""


@dataclass(frozen=True)
class ConsolidationSubmission:
    reasoning: ConsolidationReasoning
    journal: ConsolidationJournal

    async def submit(self, request: ReasoningRequest, phase: str) -> str:
        if not self.journal.has_call(phase):
            await wait_for_reasoning(self.reasoning.gateway)
        result = self.journal.recorded_call((phase, request))
        if result is None:
            result = await self.reasoning.invoke(request)
            self.journal.complete_call((phase, result))
        return result.text

    async def decode(self, submission: tuple[str, ReasoningRequest],
                     decoder: Callable[[str], T]) -> T:
        phase, request = submission
        text = await self.submit(request, phase)
        validation: dict[str, Any] = {"initial": _validation(text)}
        try:
            decoded = decoder(text)
        except (ValueError, ConsolidationCoverageMissing) as initial_error:
            validation["initial"]["error"] = str(initial_error)
            if isinstance(initial_error, ConsolidationCoverageMissing):
                validation["initial"]["required_authority_refs"] = _object(request.prompt)["authority_refs"]
                validation["initial"]["missing_authority_refs"] = list(initial_error.missing_refs)
            self.journal.record((phase + "-validation.json", validation))
            try:
                protected = _protected_content(request.purpose, text)
                correction = (coverage_correction_request(request, initial_error)
                    if isinstance(initial_error, ConsolidationCoverageMissing)
                    else self.reasoning.correction_request(request, ConsolidationCorrection(text, str(initial_error))))
            except (ConsolidationProtocolFailure, ConsolidationContextLimit) as error:
                validation["disposition"] = "rejected"
                validation["correction_error"] = str(error)
                self.journal.record((phase + "-validation.json", validation))
                raise
            # Reuse the historical correction slot for either correction kind, never both.
            # Admission/transport failures remain outside validation handling and cannot replay.
            repaired = await self.submit(correction, phase + "-format-correction")
            validation["correction"] = _validation(repaired)
            try:
                decoded = decoder(repaired)
                revised = _protected_content(request.purpose, repaired)
                if any(revised.get(key) != value for key, value in protected.items()):
                    raise ValueError("format correction changed previous semantic content")
                if isinstance(initial_error, ConsolidationCoverageMissing):
                    if not isinstance(decoded, ConsolidationReplacement):
                        raise ValueError("coverage correction did not produce a replacement")
                    protect_coverage(initial_error, decoded)
            except (ValueError, ConsolidationCoverageMissing, ConsolidationProtocolFailure) as final_error:
                validation["correction"]["error"] = str(final_error)
                validation["disposition"] = "rejected"
                self.journal.record((phase + "-validation.json", validation))
                raise ConsolidationProtocolFailure(
                    "initial validation: " + str(initial_error) + "; correction validation: " + str(final_error)
                ) from final_error
        except ConsolidationProtocolFailure as error:
            validation["initial"]["error"] = str(error)
            validation["disposition"] = "rejected"
            self.journal.record((phase + "-validation.json", validation))
            raise
        validation["disposition"] = "accepted"
        self.journal.record((phase + "-validation.json", validation))
        return decoded


def _validation(text: str) -> dict[str, object]:
    return {"wrapper_normalized": _normalise_json_object(text) != text.strip(), "error": None}


def _protected_content(purpose: str, text: str) -> dict[str, str]:
    """Recover protected decoded values without rewriting any semantic content."""
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
