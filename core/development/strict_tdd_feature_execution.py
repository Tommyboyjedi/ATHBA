"""Concrete feature scenario execution and final accepted-evidence reconciliation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.development.microcycle_revision_service import MicrocycleRevisionLifecycle
from core.development.microcycle_revision_state import (
    RevisionBindingRequest,
    RevisionInitialisationRequest,
    RevisionRecoveryRequest,
)
from core.development.project_environment import ProjectEnvironmentService
from core.development.project_revision_synchronization import TrustedProjectRevisionSynchronizer
from core.development.scenario_drafting import ScenarioDraftingService
from core.development.scenario_drafting_domain import ScenarioDraftRequest, ScenarioRepositoryFacts
from core.development.specification_reconciliation import (
    ChecklistItemReconciler,
    ChecklistReconciliationRequest,
    CompletedMicrocycleEvidenceCollector,
    GitAcceptedTestCatalog,
)
from core.development.strict_microcycle import StrictMicrocycleRequest, StrictMicrocycleService
from core.development.strict_tdd_feature_application import (
    FeatureReconciliationRequest,
    FeatureScenarioRequest,
    FeatureScenarioResult,
)
from core.development.tdd_progression import SpecificationGatekeeperRunState, TddStepProposal
from core.execution.reasoning_gateway import ReasoningGateway


@dataclass(frozen=True)
class StrictFeatureScenarioDependencies:
    drafting: ScenarioDraftingService
    microcycles: StrictMicrocycleService
    revisions: MicrocycleRevisionLifecycle
    environment: ProjectEnvironmentService


class StrictFeatureScenarioExecutor:
    """Executes one selected behavior through draft, strict microcycles, and completion."""

    def __init__(self, dependencies: StrictFeatureScenarioDependencies):
        self.drafting = dependencies.drafting
        self.microcycles = dependencies.microcycles
        self.revisions = dependencies.revisions
        self.synchronizer = TrustedProjectRevisionSynchronizer(dependencies.environment)

    async def execute(self, request: FeatureScenarioRequest) -> FeatureScenarioResult:
        ticket = _ticket_for(request)
        scenario_id = f"{request.project.project_id}--{request.behavior.ref}"
        draft = await self.drafting.draft(
            ScenarioDraftRequest(
                scenario_id, ticket, tuple(request.behavior.source_refs), "python", "pytest",
                ticket.test_path, _facts(Path(request.project.repository_root), request.canonical_development_base, ticket),
                request.canonical_development_base,
            ),
            request.project.binding().with_base_sha(request.canonical_development_base),
        )
        if not draft.approved or draft.state.approved_microcycle is None:
            return FeatureScenarioResult(
                request.behavior.ref, scenario_id, "scenario_draft_blocked",
                f"refs/heads/{request.project.default_ref}", request.canonical_development_base,
                None, None, blocked_reason=draft.state.status,
            )
        binding_request = RevisionBindingRequest(
            scenario_id, request.project.project_id, request.project.repository_root,
            tuple(request.project.runtime.resource_paths()),
        )
        self.revisions.initialise(
            RevisionInitialisationRequest(
                scenario_id, f"refs/heads/{request.project.default_ref}",
                request.canonical_development_base, (f"scenario-draft:{scenario_id}",),
            )
        )
        outcome = await self.microcycles.run(
            StrictMicrocycleRequest(
                request.project.project_id, ticket.production_path, Path(request.project.repository_root),
                request.project.binding().with_base_sha(request.canonical_development_base),
                draft.state.approved_microcycle, (), True, self.revisions, binding_request,
            )
        )
        lifecycle = self.revisions.recover(RevisionRecoveryRequest(scenario_id))
        if outcome.status != "behavior_complete":
            return FeatureScenarioResult(
                request.behavior.ref, scenario_id, outcome.status, lifecycle.canonical_ref,
                lifecycle.canonical_development_base, lifecycle.working_ref,
                lifecycle.working_revision, _evidence(outcome.state), outcome.status,
            )
        self.synchronizer.synchronize(request.project.project_id, lifecycle.canonical_development_base)
        return FeatureScenarioResult(
            request.behavior.ref, scenario_id, "behavior_complete", lifecycle.canonical_ref,
            lifecycle.canonical_development_base, None, None, _evidence(outcome.state),
        )


@dataclass(frozen=True)
class CompletedFeatureReconciler:
    """Reconciles only completed strict-microcycle evidence against the final Git revision."""

    repository_root: Path
    state_store: MicrocycleStateRepo
    reasoning_gateway: ReasoningGateway

    async def reconcile(
        self, request: FeatureReconciliationRequest
    ) -> tuple[dict[str, object], ...]:
        gatekeeper = SpecificationGatekeeperRunState.from_dict(request.gatekeeper_payload)
        states = [self._state(item.scenario_id) for item in request.completed_behaviors]
        accepted = CompletedMicrocycleEvidenceCollector().collect(states)
        catalog = GitAcceptedTestCatalog(self.repository_root, request.canonical_revision)
        item_reconciler = ChecklistItemReconciler(self.reasoning_gateway, catalog)
        results: list[dict[str, object]] = []
        for item in gatekeeper.checklist.items:
            result = await item_reconciler.reconcile(
                ChecklistReconciliationRequest(request.contract.project_id, item.ref, item.text, accepted)
            )
            results.append(result.to_dict())
        return tuple(results)

    def _state(self, scenario_id: str):
        state = self.state_store.load(scenario_id)
        if state is None:
            raise ValueError("completed behavior evidence state is unavailable")
        return state


def _ticket_for(request: FeatureScenarioRequest) -> TddStepProposal:
    index = request.contract.requirement_refs().index(request.behavior.ref)
    test_path = request.contract.test_paths[min(index, len(request.contract.test_paths) - 1)]
    production_path = request.contract.production_paths[0]
    name = "test_" + "".join(char if char.isalnum() else "_" for char in request.behavior.ref).strip("_")
    return TddStepProposal(
        request.behavior.ref, [request.behavior.ref], request.behavior.summary,
        f"{test_path}::{name}", request.behavior.observable_outcome, test_path, production_path,
        request.behavior.test_hint, request.behavior.observable_outcome,
        "next dependency-ready observable behavior",
    )


def _facts(root: Path, revision: str, ticket: TddStepProposal) -> ScenarioRepositoryFacts:
    paths = tuple(_git(root, "ls-tree", "-r", "--name-only", revision).splitlines())
    return ScenarioRepositoryFacts(
        revision, paths, _show(root, revision, ticket.production_path),
        _show(root, revision, ticket.test_path),
    )


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _show(root: Path, revision: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"], cwd=root, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def _evidence(state: object) -> tuple[str, ...]:
    values = tuple(getattr(state, "regression").evidence_refs)
    review = tuple(getattr(state, "behavior_review").evidence_refs)
    return values + review or (f"microcycle:{getattr(state, 'scenario_draft').scenario_id}",)
