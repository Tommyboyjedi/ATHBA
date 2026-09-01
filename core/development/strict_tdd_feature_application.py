"""Small feature-level coordinator over strict-TDD services and persisted feature state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from core.development.behavior_contract_coordinator import BehaviorContractPlanner, ContractPlanningRequest
from core.development.behavior_contract_domain import BehaviorContract, BehaviorContractRequirement
from core.development.project_environment import DevelopmentProject, ProjectEnvironmentService
from core.development.specification_assessment import GatekeeperStateRequest, SpecificationGatekeeper
from core.development.strict_tdd_feature_domain import (
    CompletedBehaviorReference,
    StrictTddFeatureRequest,
    StrictTddFeatureResult,
    StrictTddFeatureState,
    StrictTddFeatureStatus,
)
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository


@dataclass(frozen=True)
class FeatureScenarioRequest:
    project: DevelopmentProject
    contract: BehaviorContract
    behavior: BehaviorContractRequirement
    canonical_development_base: str


@dataclass(frozen=True)
class FeatureScenarioResult:
    behavior_ref: str
    scenario_id: str
    status: str
    canonical_ref: str
    canonical_development_base: str
    working_ref: str | None
    working_revision: str | None
    evidence_refs: tuple[str, ...] = ()
    blocked_reason: str | None = None


@dataclass(frozen=True)
class FeatureReconciliationRequest:
    contract: BehaviorContract
    completed_behaviors: tuple[CompletedBehaviorReference, ...]
    gatekeeper_payload: dict[str, object]
    canonical_revision: str


class FeatureScenarioExecutor(Protocol):
    async def execute(self, request: FeatureScenarioRequest) -> FeatureScenarioResult: ...


class FeatureReconciler(Protocol):
    async def reconcile(
        self, request: FeatureReconciliationRequest
    ) -> tuple[dict[str, object], ...]: ...


@dataclass(frozen=True)
class StrictTddFeatureDependencies:
    environment: ProjectEnvironmentService
    state_repository: StrictTddFeatureRepository
    contract_planner: BehaviorContractPlanner
    gatekeeper: SpecificationGatekeeper
    scenarios: FeatureScenarioExecutor
    reconciler: FeatureReconciler


class StrictTddFeatureApplicationService:
    """Coordinates feature checkpoints while inner services retain their state machines."""

    def __init__(self, dependencies: StrictTddFeatureDependencies):
        self.environment = dependencies.environment
        self.states = dependencies.state_repository
        self.contract_planner = dependencies.contract_planner
        self.gatekeeper = dependencies.gatekeeper
        self.scenarios = dependencies.scenarios
        self.reconciler = dependencies.reconciler

    async def run(self, request: StrictTddFeatureRequest) -> StrictTddFeatureResult:
        project = self.environment.create_or_load_python_project(request.project_id)
        state = await self.plan(request, project)
        contract = BehaviorContract.from_dict(dict(state.contract_payload or {}), load_options=None)
        if state.status == StrictTddFeatureStatus.COMPLETED.value:
            return _result(project, state)
        for behavior in contract.observable_requirements:
            if behavior.ref in {item.behavior_ref for item in state.completed_behaviors}:
                continue
            outcome = await self.scenarios.execute(
                FeatureScenarioRequest(
                    project, contract, behavior,
                    state.canonical_development_base or project.trusted_base_sha,
                )
            )
            state = self._after_scenario(state, outcome)
            self.states.save(state)
            if state.status == StrictTddFeatureStatus.BLOCKED.value:
                return _result(project, state)
        reconciliation = await self.reconciler.reconcile(
            FeatureReconciliationRequest(
                contract, state.completed_behaviors, dict(state.gatekeeper_payload or {}),
                str(state.canonical_development_base),
            )
        )
        completed = replace(
            state, status=StrictTddFeatureStatus.COMPLETED.value, current_scenario_id=None,
            working_ref=None, working_revision=None, final_reconciliation=reconciliation,
        )
        self.states.save(completed)
        return _result(project, completed)

    async def plan(
        self, request: StrictTddFeatureRequest, project: DevelopmentProject
    ) -> StrictTddFeatureState:
        existing = self.states.load(request.project_id)
        if existing is not None:
            if existing.source_requirement_hash != request.source_requirement_hash:
                raise ValueError("feature state source requirement identity diverged")
            return existing
        contract = await self.contract_planner.create_contract(
            ContractPlanningRequest(
                request.project_id, request.source_requirement,
                list(request.production_paths), list(request.test_paths),
            )
        )
        checklist = await self.gatekeeper.ensure_state(GatekeeperStateRequest(contract, None))
        state = StrictTddFeatureState(
            request.project_id, request.source_requirement_hash, StrictTddFeatureStatus.RUNNING.value,
            contract.to_dict(), checklist.to_dict(), canonical_ref=f"refs/heads/{project.default_ref}",
            canonical_development_base=project.trusted_base_sha,
        )
        self.states.save(state)
        return state

    def _after_scenario(
        self, state: StrictTddFeatureState, outcome: FeatureScenarioResult
    ) -> StrictTddFeatureState:
        if outcome.status != "behavior_complete":
            return replace(
                state, status=StrictTddFeatureStatus.BLOCKED.value,
                current_scenario_id=outcome.scenario_id, canonical_ref=outcome.canonical_ref,
                canonical_development_base=outcome.canonical_development_base,
                working_ref=outcome.working_ref, working_revision=outcome.working_revision,
                blocked_reason=outcome.blocked_reason or outcome.status,
                evidence_refs=(*state.evidence_refs, *outcome.evidence_refs),
            )
        completed = CompletedBehaviorReference(
            outcome.behavior_ref, outcome.scenario_id, outcome.canonical_development_base,
            outcome.evidence_refs,
        )
        return replace(
            state, current_scenario_id=None, canonical_ref=outcome.canonical_ref,
            canonical_development_base=outcome.canonical_development_base,
            working_ref=None, working_revision=None,
            completed_behaviors=(*state.completed_behaviors, completed),
            evidence_refs=(*state.evidence_refs, *outcome.evidence_refs),
        )


def _result(project: DevelopmentProject, state: StrictTddFeatureState) -> StrictTddFeatureResult:
    return StrictTddFeatureResult(
        state.project_id, project.repository_root, state.status, state.canonical_ref,
        state.canonical_development_base, state.working_ref, state.working_revision,
        state.current_scenario_id, state.completed_behaviors, state.blocked_reason,
        state.final_reconciliation, state.evidence_refs,
    )
