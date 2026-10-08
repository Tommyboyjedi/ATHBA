"""Small source-grounded distinctions, independent of target language syntax."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.development.specification_domain import SourceRequirementClause
    from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement

from enum import Enum
import re

from core.development.specification_provenance import resolve_source_quote


class ObligationType(str, Enum):
    BEHAVIOR = "observable_behavior"
    PRECONDITION = "precondition"
    ERROR_BEHAVIOR = "error_behavior"
    INVARIANT = "invariant"
    MECHANICAL = "mechanical_assurance"
    NON_PERSISTENCE = "non_persistence_assurance"
    NAMING = "naming"


ERROR_ACTION = re.compile(
    r"\b(?:reject\w*|rais(?:e|es|ed|ing)|throw\w*|errors?|exceptions?)\b"
    r"|\b(?:invalid|unsupported)\b.{0,80}\b(?:return\w*|fail\w*)\b", re.I)
ERROR_IDENTIFIER = re.compile(r"\b[A-Z]\w*(?:Error|Exception)\b")
NON_PERSISTENCE = re.compile(
    r"\bin[- ]memory\b|\b(?:no|without|not|never)\b.{0,70}"
    r"\b(?:persist\w*|database\w*|storage|files?|disk)\b", re.I)
PERSISTENCE = re.compile(r"\b(?:persist\w*|database\w*|storage|files?|disk)\b", re.I)
POSITIVE_PERSISTENCE = re.compile(r"\bpersist\w*\b|\b(?:save|store|retain)\w*\b.{0,80}\b(?:files?|disk|database|sessions?|restarts?)\b", re.I)
LEXICAL_NAME = re.compile(r"\b(?:named|identifier|spelling|exact name|required_name)\b", re.I)


def explicit_error(text: str) -> bool:
    return bool(ERROR_ACTION.search(text) or ERROR_IDENTIFIER.search(text))


def classify_obligation(subject: str, kind: str) -> ObligationType:
    if kind in {"constraint", "quality"}:
        if NON_PERSISTENCE.search(subject):
            return ObligationType.NON_PERSISTENCE
        if POSITIVE_PERSISTENCE.search(subject):
            return ObligationType.BEHAVIOR
        if LEXICAL_NAME.search(subject):
            return ObligationType.NAMING
        return ObligationType.MECHANICAL
    if explicit_error(subject):
        return ObligationType.ERROR_BEHAVIOR
    if kind == "validation":
        return ObligationType.PRECONDITION
    if kind == "invariant":
        return ObligationType.INVARIANT
    return ObligationType.BEHAVIOR


def classification_subject(subject: str, kind: str, quote: str) -> str:
    if kind == "validation" and explicit_error(quote):
        return quote
    if kind in {"constraint", "quality"} and LEXICAL_NAME.search(quote):
        return quote
    if kind in {"constraint", "quality"} and PERSISTENCE.search(subject) and NON_PERSISTENCE.search(quote):
        return quote
    return subject


def validated_type(subject: str, kind: str, supplied: str = "") -> str:
    expected = classify_obligation(subject, kind)
    if supplied and ObligationType(supplied) != expected:
        raise ValueError("obligation classification disagrees with the source subject/kind")
    return expected.value


def validate_error_authority(claim: str, source: str) -> None:
    if explicit_error(claim) and not explicit_error(source):
        raise ValueError("source does not specify rejection or error behavior")
    invented = set(ERROR_IDENTIFIER.findall(claim)) - set(ERROR_IDENTIFIER.findall(source))
    if invented:
        raise ValueError(f"error identifier is not specified by source: {sorted(invented)}")


def clause_source_context(clause: SourceRequirementClause, source: str) -> str:
    if not clause.source_quote:
        validate_error_authority(clause.text, source)
        return source
    provenance = resolve_source_quote(source, clause.source_quote)
    if not clause.subject or not provenance.grounds_subject(clause.subject):
        raise ValueError("source clause subject is not grounded in retained source")
    validated_type(classification_subject(clause.subject, clause.kind, clause.source_quote), clause.kind, clause.obligation_type)
    validate_error_authority(clause.text, provenance.context)
    return provenance.context


def validate_behavior_authority(contract: BehaviorContract, requirement: BehaviorContractRequirement) -> None:
    clauses = [clause for clause in contract.source_clauses if clause.ref in requirement.source_refs]
    source = " ".join(clause.source_context(contract.requirement_source) for clause in clauses)
    for claim in (requirement.summary, requirement.observable_outcome,
                  requirement.test_hint, requirement.error_expectation or ""):
        validate_error_authority(claim, source)


def validate_planned_clauses(clauses: list[SourceRequirementClause], source: str) -> None:
    for clause in clauses:
        if not clause.source_quote or not clause.subject:
            raise ValueError(f"new source clause requires grounded source_quote and subject: {clause.ref}")
        clause.source_context(source)
        behavioral = clause.obligation_type in {ObligationType.BEHAVIOR.value, ObligationType.INVARIANT.value,
            ObligationType.ERROR_BEHAVIOR.value, ObligationType.PRECONDITION.value}
        if behavioral and clause.evidence_kind != "test":
            raise ValueError("observable/domain source clauses require the behavioral evidence channel: " + clause.ref)
        if not behavioral and clause.evidence_kind == "test":
            raise ValueError("assurance/naming source clauses cannot require a behavioral RED: " + clause.ref)

def validate_contract_authority(contract: BehaviorContract) -> None:
    """Validate a new semantic proposal, not historical malformed repair evidence."""
    for requirement in contract.observable_requirements:
        validate_behavior_authority(contract, requirement)
        clauses = [c for c in contract.source_clauses if c.ref in requirement.source_refs]
        if not any(c.evidence_kind == "test" and c.obligation_type in {ObligationType.BEHAVIOR.value, ObligationType.ERROR_BEHAVIOR.value, ObligationType.INVARIANT.value}
                   for c in clauses):
            raise ValueError("observable requirements must include at least one test-evidence source clause: "
                             + requirement.ref)
    for claim in contract.error_semantics:
        validate_error_authority(claim, contract.requirement_source)
