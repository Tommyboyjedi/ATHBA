from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, TypeVar

from core.development.tdd_progression_values import ChecklistEvidenceKind, ChecklistItemKind

if TYPE_CHECKING:
    from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement

EnumValue = TypeVar("EnumValue", bound=Enum)


def enum_value(value: str | Enum, enum_type: type[EnumValue], label: str) -> str:
    try:
        return enum_type(str(value)).value
    except ValueError as error:
        raise ValueError(f"unsupported {label}: {value}") from error


def require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty")


def validate_commands(commands: list[list[str]], label: str) -> None:
    if not commands:
        raise ValueError(f"{label} must not be empty")
    for command in commands:
        if not command:
            raise ValueError(f"{label} must not contain empty commands")
        if any(not isinstance(arg, str) or not arg for arg in command):
            raise ValueError(f"{label} must contain non-empty string arguments")


def validate_list_of_strings(values: list[str], label: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{label} must contain non-empty strings")


def list_of_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    result = [str(item) for item in value]
    validate_list_of_strings(result, label)
    return result


def validate_repository_relative_paths(values: list[str], label: str) -> None:
    validate_list_of_strings(values, label)
    for value in values:
        validate_repository_relative_path(value, label)


def validate_allowed_path_subset(values: list[str], allowed: list[str] | None, label: str) -> None:
    if allowed is None or not allowed:
        return
    disallowed = [value for value in values if value not in allowed]
    if disallowed:
        raise ValueError(f"{label} must be selected from the allowed path set")


def validate_unique_refs(refs: list[str], label: str) -> None:
    duplicates = sorted({ref for ref in refs if refs.count(ref) > 1})
    if duplicates:
        raise ValueError(f"duplicate {label} are not allowed: {duplicates}")


def validate_contract_source_coverage(contract: BehaviorContract) -> None:
    clause_refs = contract.source_clause_refs()
    clause_ref_set = set(clause_refs)
    seen_source_refs: set[str] = set()
    for requirement in contract.observable_requirements:
        for source_ref in requirement.source_refs:
            if source_ref not in clause_ref_set:
                raise ValueError(f"requirement source refs must exist in source clauses: {source_ref}")
            seen_source_refs.add(source_ref)
    uncovered = [ref for ref in clause_refs if ref not in seen_source_refs]
    if uncovered:
        raise ValueError(f"source clauses must be covered by observable requirements: {uncovered}")


def validate_requirement_dependencies(requirements: list[BehaviorContractRequirement]) -> None:
    refs = {requirement.ref for requirement in requirements}
    dependencies = {requirement.ref: set(requirement.depends_on) for requirement in requirements}
    unknown = {dependency for values in dependencies.values() for dependency in values} - refs
    if unknown:
        raise ValueError(f"requirement dependencies must reference the contract: {sorted(unknown)}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visiting:
            raise ValueError("requirement dependencies must be acyclic")
        if ref in visited:
            return
        visiting.add(ref)
        for dependency in dependencies[ref]:
            visit(dependency)
        visiting.remove(ref)
        visited.add(ref)

    for ref in dependencies:
        visit(ref)


def default_evidence_kind(kind: str) -> str:
    normalized_kind = enum_value(kind, ChecklistItemKind, "source clause kind")
    if normalized_kind == ChecklistItemKind.QUALITY.value:
        return ChecklistEvidenceKind.REVIEW.value
    if normalized_kind == ChecklistItemKind.CONSTRAINT.value:
        return ChecklistEvidenceKind.MECHANICAL.value
    return ChecklistEvidenceKind.TEST.value


def normalize_evidence_kind(kind: str, value: object) -> str:
    if value is None:
        return default_evidence_kind(kind)
    normalized = str(value).strip()
    if not normalized:
        return default_evidence_kind(kind)
    if normalized == ChecklistItemKind.QUALITY.value:
        return ChecklistEvidenceKind.REVIEW.value
    return enum_value(normalized, ChecklistEvidenceKind, "checklist evidence kind")


def validate_repository_relative_path(value: str, label: str) -> None:
    candidate = PurePosixPath(value.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"{label} must contain repository-relative paths")
    if "/" not in candidate.as_posix() and "." not in candidate.name:
        raise ValueError(f"{label} must contain repository-relative file paths")
