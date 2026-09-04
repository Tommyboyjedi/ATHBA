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
from core.development.tdd_progression_values import (
    ContractPoolStatus,
    TechnicalBindingRole,
    TechnicalDecisionKind,
    TechnicalDecisionOrigin,
)


@dataclass(frozen=True)
class BehaviorContractLoadOptions:
    allowed_production_paths: list[str] | None = None
    allowed_test_paths: list[str] | None = None


@dataclass(frozen=True)
class TechnicalBinding:
    """One explicit binding from an observable requirement to a technical decision."""

    technical_ref: str
    role: str

    def __post_init__(self) -> None:
        require_text(self.technical_ref, "technical binding ref")
        object.__setattr__(
            self,
            "role",
            enum_value(self.role, TechnicalBindingRole, "technical binding role"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"technical_ref": self.technical_ref, "role": self.role}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TechnicalBinding":
        if not isinstance(payload, dict):
            raise ValueError("technical binding must be an object")
        return cls(
            technical_ref=payload.get("technical_ref"),
            role=payload.get("role"),
        )


@dataclass(frozen=True)
class TechnicalDecision:
    """A provider-neutral, binding code-level decision carried by a contract."""

    ref: str
    kind: str
    qualified_identifier: str
    origin: str
    source_clause_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    source_excerpt: str | None = None

    def __post_init__(self) -> None:
        require_text(self.ref, "technical decision ref")
        object.__setattr__(
            self,
            "kind",
            enum_value(self.kind, TechnicalDecisionKind, "technical decision kind"),
        )
        require_text(self.qualified_identifier, "technical decision qualified identifier")
        object.__setattr__(
            self,
            "origin",
            enum_value(self.origin, TechnicalDecisionOrigin, "technical decision origin"),
        )
        if not isinstance(self.source_clause_refs, list):
            raise ValueError("technical decision source clause refs must be a list")
        if not isinstance(self.evidence_refs, list):
            raise ValueError("technical decision evidence refs must be a list")
        validate_list_of_strings(self.source_clause_refs, "technical decision source clause refs")
        validate_list_of_strings(self.evidence_refs, "technical decision evidence refs")
        if self.source_excerpt is not None:
            require_text(self.source_excerpt, "technical decision source excerpt")
        if self.origin == TechnicalDecisionOrigin.SOURCE_REQUIREMENT.value:
            if self.source_excerpt is None:
                raise ValueError("source_requirement technical decisions require a source excerpt")
            if not self.source_clause_refs:
                raise ValueError("source_requirement technical decisions require source clause refs")
        elif self.source_excerpt is not None:
            raise ValueError("only source_requirement technical decisions may carry a source excerpt")
        if self.origin == TechnicalDecisionOrigin.UPSTREAM_DESIGN.value and not self.evidence_refs:
            raise ValueError("upstream_design technical decisions require provenance evidence refs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "kind": self.kind,
            "qualified_identifier": self.qualified_identifier,
            "origin": self.origin,
            "source_clause_refs": list(self.source_clause_refs),
            "evidence_refs": list(self.evidence_refs),
            "source_excerpt": self.source_excerpt,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TechnicalDecision":
        if not isinstance(payload, dict):
            raise ValueError("technical decision must be an object")
        return cls(
            ref=payload.get("ref"),
            kind=payload.get("kind"),
            qualified_identifier=payload.get("qualified_identifier"),
            origin=payload.get("origin"),
            source_clause_refs=list_of_strings(
                payload.get("source_clause_refs", []),
                "technical decision source clause refs",
            ),
            evidence_refs=list_of_strings(
                payload.get("evidence_refs", []),
                "technical decision evidence refs",
            ),
            source_excerpt=payload.get("source_excerpt"),
        )


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
    technical_bindings: list[TechnicalBinding] = field(default_factory=list)

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
        if not isinstance(self.technical_bindings, list):
            raise ValueError("requirement technical bindings must be a list")
        if not all(isinstance(item, TechnicalBinding) for item in self.technical_bindings):
            raise ValueError("requirement technical bindings must contain technical bindings")
        binding_keys = [(item.technical_ref, item.role) for item in self.technical_bindings]
        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError("duplicate requirement technical bindings are not allowed")

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
            "technical_bindings": [item.to_dict() for item in self.technical_bindings],
        }

    def to_model_dict(self) -> dict[str, Any]:
        """Retain the Phase 1 boundary: current model payloads omit bindings."""
        payload = self.to_dict()
        payload.pop("technical_bindings")
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BehaviorContractRequirement":
        if not isinstance(payload, dict):
            raise ValueError("requirement must be an object")
        bindings = payload.get("technical_bindings", [])
        if not isinstance(bindings, list):
            raise ValueError("requirement technical bindings must be a list")
        return cls(
            ref=str(payload["ref"]),
            source_refs=list_of_strings(payload.get("source_refs"), "requirement source refs"),
            summary=str(payload["summary"]),
            observable_outcome=str(payload["observable_outcome"]),
            test_hint=str(payload["test_hint"]),
            error_expectation=payload.get("error_expectation"),
            preserves_state_on_failure=bool(payload.get("preserves_state_on_failure", True)),
            depends_on=list_of_strings(payload.get("depends_on", []), "requirement dependencies"),
            technical_bindings=[TechnicalBinding.from_dict(item) for item in bindings],
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
    technical_decisions: list[TechnicalDecision] = field(default_factory=list)

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
        if not isinstance(self.technical_decisions, list):
            raise ValueError("technical decisions must be a list")
        if not all(isinstance(item, TechnicalDecision) for item in self.technical_decisions):
            raise ValueError("technical decisions must contain technical decisions")
        validate_unique_refs(self.technical_decision_refs(), "technical decision refs")
        validate_technical_decision_bindings(self)

    def source_clause_refs(self) -> list[str]:
        return [clause.ref for clause in self.source_clauses]

    def requirement_refs(self) -> list[str]:
        return [requirement.ref for requirement in self.observable_requirements]

    def technical_decision_refs(self) -> list[str]:
        return [decision.ref for decision in self.technical_decisions]

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
            "technical_decisions": [item.to_dict() for item in self.technical_decisions],
        }

    def to_model_dict(self) -> dict[str, Any]:
        """Preserve current Planner, Tester, and Developer prompt behavior in Phase 1."""
        payload = self.to_dict()
        payload["observable_requirements"] = [
            item.to_model_dict() for item in self.observable_requirements
        ]
        payload.pop("technical_decisions")
        return payload

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
        technical_decisions = payload.get("technical_decisions", [])
        if not isinstance(technical_decisions, list):
            raise ValueError("technical_decisions must be a list")
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
            technical_decisions=[TechnicalDecision.from_dict(item) for item in technical_decisions],
        )
        options = load_options or BehaviorContractLoadOptions()
        validate_allowed_path_subset(contract.production_paths, options.allowed_production_paths, "production paths")
        validate_allowed_path_subset(contract.test_paths, options.allowed_test_paths, "test paths")
        return contract

def validate_technical_decision_bindings(contract: BehaviorContract) -> None:
    """Fail closed when an explicit technical decision lacks valid traceability."""
    source_clause_refs = set(contract.source_clause_refs())
    technical_refs = set(contract.technical_decision_refs())
    bound_refs: set[str] = set()
    for decision in contract.technical_decisions:
        unknown_source_refs = set(decision.source_clause_refs) - source_clause_refs
        if unknown_source_refs:
            raise ValueError(
                "technical decision source clause refs must exist in source clauses: "
                f"{sorted(unknown_source_refs)}"
            )
        if decision.origin == TechnicalDecisionOrigin.SOURCE_REQUIREMENT.value:
            assert decision.source_excerpt is not None
            if decision.source_excerpt not in contract.requirement_source:
                raise ValueError(
                    "technical decision source excerpt must be an exact substring "
                    "of requirement source"
                )
            if decision.qualified_identifier not in decision.source_excerpt:
                raise ValueError(
                    "source_requirement technical decision identifier must appear "
                    "in its source excerpt"
                )
    for requirement in contract.observable_requirements:
        for binding in requirement.technical_bindings:
            if binding.technical_ref not in technical_refs:
                raise ValueError(
                    "technical binding ref must exist in technical decisions: "
                    f"{binding.technical_ref}"
                )
            bound_refs.add(binding.technical_ref)
    unbound = technical_refs - bound_refs
    if unbound:
        raise ValueError(
            "technical decisions must be bound to observable requirements: "
            f"{sorted(unbound)}"
        )
