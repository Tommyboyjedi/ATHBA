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
NAMING_OUTPUT_FORMAT = (
    "NO\n"
    "or:\n"
    "YES\n"
    "current_name: <exact existing identifier>\n"
    "required_name: <exact required identifier>"
)
NAMING_INSTRUCTION = (
    "Compare the explicitly required identifier names with the production code. "
    "A naming mismatch exists only when an explicitly required identifier is absent "
    "and the same public/product concept is implemented under a different identifier. "
    "If the required identifier already exists in production, answer NO. "
    "Do not suggest removal of aliases or duplicate helpers, syntax changes, API-shape changes, "
    "style improvements, general cleanup or refactoring. "
    "Return exactly either:\n"
    f"{NAMING_OUTPUT_FORMAT}\n"
    "Do not add punctuation, explanation, markdown, or any other text."
)
REFACTOR_OUTPUT_FORMAT = (
    "NO\n"
    "or:\n"
    "YES\n"
    "objective: <one bounded objective>\n"
    "reason: <one brief reason>"
)
REFACTOR_INSTRUCTION = (
    "Review only the production code below. Answer NO unless one specific, material, high-confidence "
    "improvement to simplicity, duplication, efficiency or maintainability preserves its public "
    "interface and externally observable behavior. Do not propose public renaming, new behavior, "
    "test changes, broad architecture changes, speculative abstractions or style-only churn. "
    "Return at most one opportunity, exactly:\n"
    f"{REFACTOR_OUTPUT_FORMAT}."
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
        context: dict[str, object] = {
            "explicit_behavior_naming": {
                "text": request.material.text,
                "required_identifiers": list(request.material.required_identifiers),
            },
            "production": _production_context(request.production),
        }
        return await _reason_with_one_correction(
            self.reasoning,
            "identifier_requirement_comparison",
            NAMING_INSTRUCTION,
            NAMING_OUTPUT_FORMAT,
            context,
            lambda raw: parse_naming_decision(raw, request),
            "naming assessment",
        )


class RefactorAssessor:
    """Ask one conservative structural question with production source only."""

    def __init__(self, reasoning: LocalOnlyPostBehaviorReasoning):
        self.reasoning = reasoning

    async def reason(self, production: FocusedProductionSlice) -> RefactorDecision:
        context: dict[str, object] = {"production": _production_context(production)}
        return await _reason_with_one_correction(
            self.reasoning,
            "bounded_structure_assessment",
            REFACTOR_INSTRUCTION,
            REFACTOR_OUTPUT_FORMAT,
            context,
            parse_refactor_decision,
            "refactor assessment",
        )


async def _reason_with_one_correction(
    reasoning: LocalOnlyPostBehaviorReasoning,
    purpose: str,
    instruction: str,
    output_format: str,
    context: dict[str, object],
    parser,
    boundary: str,
):
    answer = await reasoning.reason(ReasoningRequest(
        purpose, _assessment_prompt(instruction, context), "",
    ))
    try:
        return parser(answer.text)
    except ValueError as first_error:
        correction = await reasoning.reason(ReasoningRequest(
            f"{purpose}_format_correction",
            _correction_prompt(instruction, output_format, context, answer.text, str(first_error)),
            "",
        ))
        try:
            return parser(correction.text)
        except ValueError as correction_error:
            raise ValueError(
                f"{boundary} response validation exhausted: "
                f"initial={first_error}; correction={correction_error}"
            ) from correction_error


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


def _assessment_prompt(instruction: str, context: dict[str, object]) -> str:
    return instruction + "\n" + json.dumps(context, sort_keys=True)


def _correction_prompt(
    instruction: str,
    output_format: str,
    context: dict[str, object],
    rejected_answer: str,
    validation_error: str,
) -> str:
    return instruction + "\n" + json.dumps({
        "correction_instruction": (
            "The previous answer was rejected by ATHBA validation. Return exactly one corrected answer "
            "using the same permitted context and the required output format."
        ),
        "original_context": context,
        "rejected_answer": rejected_answer,
        "validation_error": validation_error,
        "required_output_format": output_format,
    }, sort_keys=True)


def _require_single_line(value: str, limit: int) -> None:
    if not value.strip() or "\n" in value or "\r" in value or len(value) > limit:
        raise ValueError("assessment fields must be non-empty bounded single lines")
