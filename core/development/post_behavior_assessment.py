"""Tiny, deliberately isolated post-behavior assessor boundaries."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from core.development.post_behavior_slice import FocusedProductionSlice
from core.development.post_behavior_rename import declared_identifier_names
from core.execution.local_only_post_behavior_reasoning import LocalOnlyPostBehaviorReasoning
from core.execution.reasoning_gateway import ReasoningRequest

MAX_OBJECTIVE_CHARACTERS = 400
MAX_REASON_CHARACTERS = 240
IDENTIFIER_PATTERN = r"[A-Za-z_][A-Za-z_0-9]*"
NAMING_INSTRUCTION = (
    "Compare only the explicit identifier requirements with the production code below. "
    "Identify at most one public/product identifier implemented under a different name. "
    "Do not invent names or suggest style improvements. Answer NO unless there is an exact mismatch. "
    "Otherwise return exactly: YES\\ncurrent_name: <identifier>\\nrequired_name: <identifier>."
)
REFACTOR_INSTRUCTION = (
    "Review only the production code below. Answer NO unless one specific, material, high-confidence "
    "improvement to simplicity, duplication, efficiency or maintainability preserves its public "
    "interface and externally observable behavior. Do not propose public renaming, new behavior, "
    "test changes, broad architecture changes, speculative abstractions or style-only churn. "
    "Return at most one opportunity, exactly: YES\\nobjective: <one bounded objective>"
    "\\nreason: <one brief reason>, or NO."
)


@dataclass(frozen=True)
class IdentifierRename:
    current_name: str
    required_name: str

    def __post_init__(self) -> None:
        if not all(re.fullmatch(IDENTIFIER_PATTERN, item) for item in (self.current_name, self.required_name)):
            raise ValueError("rename must contain two exact identifiers")
        if self.current_name == self.required_name:
            raise ValueError("rename must change an identifier")


@dataclass(frozen=True)
class NamingDecision:
    rename: IdentifierRename | None = None


@dataclass(frozen=True)
class RefactorOpportunity:
    objective: str
    reason: str

    def __post_init__(self) -> None:
        _require_single_line(self.objective, MAX_OBJECTIVE_CHARACTERS)
        _require_single_line(self.reason, MAX_REASON_CHARACTERS)


@dataclass(frozen=True)
class RefactorDecision:
    opportunity: RefactorOpportunity | None = None


@dataclass(frozen=True)
class NamingMaterial:
    text: str
    required_identifiers: tuple[str, ...]

    def __post_init__(self) -> None:
        if any(re.fullmatch(IDENTIFIER_PATTERN, name) is None for name in self.required_identifiers):
            raise ValueError("explicit naming authority must contain exact identifiers")


@dataclass(frozen=True)
class NamingAssessmentInput:
    material: NamingMaterial
    production: FocusedProductionSlice


class NamingAssessor:
    """Ask one exact naming question with only explicit authority and focused source."""

    def __init__(self, reasoning: LocalOnlyPostBehaviorReasoning):
        self.reasoning = reasoning

    async def reason(self, request: NamingAssessmentInput) -> NamingDecision:
        context = {
            "explicit_behavior_naming": {
                "text": request.material.text,
                "required_identifiers": list(request.material.required_identifiers),
            },
            "production": _production_context(request.production),
        }
        answer = await self.reasoning.reason(ReasoningRequest(
            "identifier_requirement_comparison", NAMING_INSTRUCTION + "\n" + json.dumps(context), "",
        ))
        return parse_naming_decision(answer.text, request)


class RefactorAssessor:
    """Ask one conservative structural question with production source only."""

    def __init__(self, reasoning: LocalOnlyPostBehaviorReasoning):
        self.reasoning = reasoning

    async def reason(self, production: FocusedProductionSlice) -> RefactorDecision:
        answer = await self.reasoning.reason(ReasoningRequest(
            "bounded_structure_assessment",
            REFACTOR_INSTRUCTION + "\n" + json.dumps({"production": _production_context(production)}),
            "",
        ))
        return parse_refactor_decision(answer.text)


def parse_naming_decision(raw: str, request: NamingAssessmentInput) -> NamingDecision:
    if raw.strip() == "NO":
        return NamingDecision()
    match = re.fullmatch(
        rf"YES\ncurrent_name: ({IDENTIFIER_PATTERN})\nrequired_name: ({IDENTIFIER_PATTERN})",
        raw.strip(),
    )
    if match is None:
        # The user-facing exact mapping form is equivalent to the documented three-line form.
        match = re.fullmatch(rf"({IDENTIFIER_PATTERN}) -> ({IDENTIFIER_PATTERN})", raw.strip())
    if match is None:
        raise ValueError("naming assessment must return NO or exactly one mapping")
    rename = IdentifierRename(*match.groups())
    if rename.required_name not in request.material.required_identifiers:
        raise ValueError("required identifier has no explicit Behavior authority")
    if rename.current_name not in declared_identifier_names(request.production.files):
        raise ValueError("current identifier is absent from focused production declarations")
    return NamingDecision(rename)


def parse_refactor_decision(raw: str) -> RefactorDecision:
    if raw.strip() == "NO":
        return RefactorDecision()
    match = re.fullmatch(r"YES\nobjective: ([^\r\n]+)\nreason: ([^\r\n]+)", raw.strip())
    if match is None:
        raise ValueError("refactor assessment must return NO or one objective and brief reason")
    return RefactorDecision(RefactorOpportunity(*match.groups()))


def _production_context(production: FocusedProductionSlice) -> list[dict[str, str]]:
    return [{"path": file.path, "source": file.source} for file in production.files]


def _require_single_line(value: str, limit: int) -> None:
    if not value.strip() or "\n" in value or "\r" in value or len(value) > limit:
        raise ValueError("assessment fields must be non-empty bounded single lines")
