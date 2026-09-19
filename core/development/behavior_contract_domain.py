from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.development.specification_domain import SourceRequirementClause
from core.development.tdd_progression_validation import (
    enum_value,
    list_of_strings,
    require_text,
    validate_allowed_path_subset,
    validate_contract_source_coverage,
    validate_list_of_strings,
    validate_repository_relative_paths,
    validate_requirement_dependencies,
    validate_unique_refs,
)
from core.development.tdd_progression_values import ContractPoolStatus


@dataclass(frozen=True)
class BehaviorContractLoadOptions:
    allowed_production_paths: list[str] | None = None
    allowed_test_paths: list[str] | None = None


@dataclass(frozen=True)
class BehaviorContractRequirement:
    ref: str
    source_refs: list[str]
    summary: str
    observable_outcome: str
    test_hint: str
    error_expectation: str | None = None
    preserves_state_on_failure: bool = True
    depends_on: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        require_text(self.ref, "requirement ref")
        if not self.source_refs:
            raise ValueError("requirement source refs must not be empty")
        validate_list_of_strings(self.source_refs, "requirement source refs")
        require_text(self.summary, "requirement summary")
        require_text(self.observable_outcome, "requirement observable outcome")
        require_text(self.test_hint, "requirement test hint")
        if self.error_expectation is not None:
            require_text(self.error_expectation, "requirement error expectation")
        validate_list_of_strings(self.depends_on, "requirement dependencies")
        if self.ref in self.depends_on:
            raise ValueError("requirement cannot depend on itself")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "source_refs": list(self.source_refs),
            "summary": self.summary,
            "observable_outcome": self.observable_outcome,
            "test_hint": self.test_hint,
            "error_expectation": self.error_expectation,
            "preserves_state_on_failure": self.preserves_state_on_failure,
            "depends_on": list(self.depends_on),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BehaviorContractRequirement":
        return cls(
            ref=str(payload["ref"]),
            source_refs=list_of_strings(payload.get("source_refs"), "requirement source refs"),
            summary=str(payload["summary"]),
            observable_outcome=str(payload["observable_outcome"]),
            test_hint=str(payload["test_hint"]),
            error_expectation=payload.get("error_expectation"),
            preserves_state_on_failure=bool(payload.get("preserves_state_on_failure", True)),
            depends_on=list_of_strings(payload.get("depends_on", []), "requirement dependencies"),
        )


@dataclass(frozen=True)
class BehaviorContract:
    id: str
    project_id: str
    component_name: str
    capability: str
    requirement_source: str
    source_clauses: list[SourceRequirementClause]
    observable_requirements: list[BehaviorContractRequirement]
    invariants: list[str]
    production_paths: list[str]
    test_paths: list[str]
    public_api: list[str] = field(default_factory=list)
    error_semantics: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    completion_criteria: list[str] = field(default_factory=list)
    status: str = ContractPoolStatus.TDD_READY.value

    def __post_init__(self) -> None:
        require_text(self.id, "contract id")
        require_text(self.project_id, "project id")
        require_text(self.component_name, "component name")
        require_text(self.capability, "component capability")
        require_text(self.requirement_source, "requirement source")
        if not self.source_clauses:
            raise ValueError("source clauses must not be empty")
        if not self.observable_requirements:
            raise ValueError("observable requirements must not be empty")
        validate_unique_refs(self.source_clause_refs(), "source clause refs")
        validate_unique_refs(self.requirement_refs(), "requirement refs")
        validate_contract_source_coverage(self)
        validate_requirement_dependencies(self.observable_requirements)
        validate_list_of_strings(self.invariants, "invariants")
        validate_repository_relative_paths(self.production_paths, "production paths")
        validate_repository_relative_paths(self.test_paths, "test paths")
        validate_list_of_strings(self.public_api, "public api")
        validate_list_of_strings(self.error_semantics, "error semantics")
        validate_list_of_strings(self.non_goals, "non-goals")
        validate_list_of_strings(self.completion_criteria, "completion criteria")
        object.__setattr__(self, "status", enum_value(self.status, ContractPoolStatus, "contract status"))

    def source_clause_refs(self) -> list[str]:
        return [clause.ref for clause in self.source_clauses]

    def requirement_refs(self) -> list[str]:
        return [requirement.ref for requirement in self.observable_requirements]

    def uncovered_requirement_refs(self, completed_refs: list[str]) -> list[str]:
        completed = set(completed_refs)
        return [ref for ref in self.requirement_refs() if ref not in completed]

    def ready_requirement_refs(self, completed_refs: list[str]) -> list[str]:
        completed = set(completed_refs)
        return [
            requirement.ref
            for requirement in self.observable_requirements
            if requirement.ref not in completed and set(requirement.depends_on).issubset(completed)
        ]

    def uncovered_source_clause_refs(self) -> list[str]:
        covered = {ref for requirement in self.observable_requirements for ref in requirement.source_refs}
        return [ref for ref in self.source_clause_refs() if ref not in covered]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "component_name": self.component_name,
            "capability": self.capability,
            "requirement_source": self.requirement_source,
            "source_clauses": [item.to_dict() for item in self.source_clauses],
            "observable_requirements": [item.to_dict() for item in self.observable_requirements],
            "invariants": list(self.invariants),
            "production_paths": list(self.production_paths),
            "test_paths": list(self.test_paths),
            "public_api": list(self.public_api),
            "error_semantics": list(self.error_semantics),
            "non_goals": list(self.non_goals),
            "completion_criteria": list(self.completion_criteria),
            "status": self.status,
        }

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        load_options: BehaviorContractLoadOptions | None = None,
    ) -> "BehaviorContract":
        source_clauses = payload.get("source_clauses")
        if not isinstance(source_clauses, list):
            raise ValueError("source_clauses must be a list")
        requirements = payload.get("observable_requirements")
        if not isinstance(requirements, list):
            raise ValueError("observable_requirements must be a list")
        contract = cls(
            id=str(payload["id"]),
            project_id=str(payload["project_id"]),
            component_name=str(payload["component_name"]),
            capability=str(payload["capability"]),
            requirement_source=str(payload["requirement_source"]),
            source_clauses=[SourceRequirementClause.from_dict(dict(item)) for item in source_clauses],
            observable_requirements=[BehaviorContractRequirement.from_dict(dict(item)) for item in requirements],
            invariants=list_of_strings(payload.get("invariants"), "invariants"),
            production_paths=list_of_strings(payload.get("production_paths"), "production_paths"),
            test_paths=list_of_strings(payload.get("test_paths"), "test_paths"),
            public_api=list_of_strings(payload.get("public_api", []), "public api"),
            error_semantics=list_of_strings(payload.get("error_semantics", []), "error semantics"),
            non_goals=list_of_strings(payload.get("non_goals", []), "non-goals"),
            completion_criteria=list_of_strings(payload.get("completion_criteria", []), "completion criteria"),
            status=str(payload.get("status", ContractPoolStatus.TDD_READY.value)),
        )
        options = load_options or BehaviorContractLoadOptions()
        validate_allowed_path_subset(contract.production_paths, options.allowed_production_paths, "production paths")
        validate_allowed_path_subset(contract.test_paths, options.allowed_test_paths, "test paths")
        return contract
