"""Bounded Developer repair for a semantically rejected completed behavior."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from core.development.behavior_completion import REPAIR_REQUIRED
from core.development.deterministic_regression import (
    DeterministicRegressionRequest,
    DeterministicRegressionService,
    REGRESSION_CLEAR,
)
from core.development.microcycle_revision_service import MicrocycleRevisionLifecycle
from core.development.microcycle_revision_state import (
    RevisionBindingRequest,
    RevisionRecoveryRequest,
    RevisionTransitionKind,
    RevisionTransitionRequest,
)
from core.development.microcycle_domain import (
    BehaviorRepairExecution,
    BehaviorRepairProgress,
    BehaviorReviewVerdict,
    FinalTestMaterialisationRequest,
    LanguageTestAdapter,
    MaterialisedTestArtifact,
    MicrocycleState,
    RegressionState,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway


@dataclass(frozen=True)
class BehaviorRepairCandidateRequest:
    artifact: MaterialisedTestArtifact
    repository_root: Path
    test_path: str


class BehaviorRepairCandidate(Protocol):
    @property
    def project_root(self) -> Path: ...

    @property
    def candidate_revision(self) -> str: ...


class BehaviorRepairCandidateRepository(Protocol):
    def materialise(self, request: BehaviorRepairCandidateRequest) -> BehaviorRepairCandidate: ...
    def cleanup(self, candidate: BehaviorRepairCandidate) -> None: ...


class BehaviorRepairStateStore(Protocol):
    def save(self, state: MicrocycleState) -> object: ...


@dataclass(frozen=True)
class BehaviorRepairRequest:
    project_id: str
    production_path: str
    repository_root: Path
    repository_binding: RepositoryBinding
    state: MicrocycleState
    adapter: LanguageTestAdapter
    prior_completed_test_nodes: tuple[str, ...] = ()
    include_accepted_regression_suite: bool = True
    revision_lifecycle: MicrocycleRevisionLifecycle | None = None
    revision_binding_request: RevisionBindingRequest | None = None


@dataclass(frozen=True)
class BehaviorRepairWorkUnitRequest:
    project_id: str
    production_path: str
    artifact: MaterialisedTestArtifact
    behavior_ticket: str
    findings: tuple[str, ...]
    production_diff: str
    base_revision: str
    attempt_number: int


class BehaviorRepairWorkUnitFactory:
    """Creates a production-only packet for one completed canonical scenario."""

    def build(self, request: BehaviorRepairWorkUnitRequest) -> DevelopmentWorkUnit:
        identifier = f"{request.artifact.scenario_id}--behavior-repair-{request.attempt_number}"
        objective = json.dumps(
            {
                "role": "Developer",
                "task": "Repair the completed behavior so the approved scenario remains passing and the Senior Review findings are resolved.",
                "completed_canonical_scenario_test": request.artifact.complete_source,
                "behavior_ticket": request.behavior_ticket,
                "senior_review_findings": request.findings,
                "production_diff_evidence": request.production_diff,
                "allowed_production_path": request.production_path,
                "current_working_revision": request.base_revision,
                "constraints": [
                    "do not edit tests",
                    "do not broaden feature scope",
                    "do not use replacement source code from the review",
                    "do not perform PR21 refactoring",
                ],
            },
            sort_keys=True,
        )
        return DevelopmentWorkUnit(
            id=identifier,
            project_id=request.project_id,
            parent_ticket_id=request.artifact.scenario_id,
            objective=objective,
            allowed_paths=[request.production_path],
            acceptance=AcceptanceContract(
                [[sys.executable, "-m", "pytest", "-q", request.artifact.canonical_test_identity]],
                required_artifacts=[request.production_path],
            ),
            max_implementation_attempts=1,
            change_key=identifier,
            status=WorkUnitStatus.READY,
        )


@dataclass(frozen=True)
class BehaviorRepairDependencies:
    state_store: BehaviorRepairStateStore
    candidates: BehaviorRepairCandidateRepository
    gateway: WorkUnitExecutionGateway
    regression: DeterministicRegressionService
    factory: BehaviorRepairWorkUnitFactory = BehaviorRepairWorkUnitFactory()


@dataclass(frozen=True)
class BehaviorRepairOutcome:
    state: MicrocycleState
    status: str
    developer_submissions: int = 0


@dataclass(frozen=True)
class BehaviorRepairRegressionRequest:
    repair: BehaviorRepairRequest
    state: MicrocycleState
    developer_submissions: int = 0


class BehaviorRepairService:
    """Executes one bounded semantic repair and deterministic evidence refresh."""

    def __init__(self, dependencies: BehaviorRepairDependencies):
        self.state_store = dependencies.state_store
        self.candidates = dependencies.candidates
        self.gateway = dependencies.gateway
        self.regression = dependencies.regression
        self.factory = dependencies.factory

    async def repair(self, request: BehaviorRepairRequest) -> BehaviorRepairOutcome:
        """Compatibility API that loops over the separate repair transitions."""
        review = request.state.behavior_review
        if review.verdict == BehaviorReviewVerdict.PENDING.value and review.repair.current_candidate_revision:
            outcome = self.run_regression(request)
        else:
            outcome = await self.submit(request)
            if outcome.status == "behavior_repair_submitted":
                outcome = self.run_regression(replace(request, state=outcome.state))
        if outcome.status == "behavior_repair_regression_clear":
            promoted = self.promote(replace(request, state=outcome.state))
            return BehaviorRepairOutcome(promoted.state, outcome.status, outcome.developer_submissions)
        return outcome

    async def submit(self, request: BehaviorRepairRequest) -> BehaviorRepairOutcome:
        review = request.state.behavior_review
        if review.verdict != REPAIR_REQUIRED:
            raise ValueError("behavior repair requires a persisted repair_required review")
        if review.repair.attempts >= 4:
            exhausted = replace(
                request.state,
                behavior_review=replace(review, verdict=BehaviorReviewVerdict.ATTEMPTS_EXHAUSTED.value),
            )
            self.state_store.save(exhausted)
            return BehaviorRepairOutcome(exhausted, "behavior_repair_attempts_exhausted")
        return await self._submit(request)

    async def _submit(self, request: BehaviorRepairRequest) -> BehaviorRepairOutcome:
        state = request.state
        review = state.behavior_review
        base = review.reviewed_candidate_revision or state.completion.completed_revision or state.development_base_revision
        artifact = request.adapter.materialise_final_test(
            FinalTestMaterialisationRequest(state.model, state.fragments, base)
        )
        unit = self.factory.build(
            BehaviorRepairWorkUnitRequest(
                request.project_id, request.production_path, artifact, state.scenario_draft.behavior_ref,
                review.findings, review.production_diff, base, review.repair.attempts + 1,
            )
        )
        result = await self.gateway.execute(unit, _working_binding(request, base))
        if result.work_unit_id != unit.id:
            raise ValueError("stale Rack AI packet does not match the active behavior repair")
        if result.accepted and result.accepted_revision is not None:
            _advance_working_revision(request, result.accepted_revision, result.evidence_location)
        progress = _progress_after_submission(review.repair, unit.id, result.accepted_revision, result.evidence_location, result.error)
        if not result.accepted or result.accepted_revision is None:
            rejected = replace(state, behavior_review=replace(review, repair=progress))
            self.state_store.save(rejected)
            return BehaviorRepairOutcome(rejected, "behavior_repair_candidate_rejected", 1)
        accepted = replace(
            state,
            behavior_review=replace(
                review,
                verdict=BehaviorReviewVerdict.PENDING.value,
                repair=replace(progress, current_candidate_revision=result.accepted_revision, regression=RegressionState("pending", state.regression.command)),
            ),
            candidate_chain_revision=result.accepted_revision,
            regression=RegressionState("pending", state.regression.command),
        )
        self.state_store.save(accepted)
        return BehaviorRepairOutcome(accepted, "behavior_repair_submitted", 1)

    def run_regression(self, request: BehaviorRepairRequest) -> BehaviorRepairOutcome:
        return self._regress(BehaviorRepairRegressionRequest(request, request.state))

    def _regress(self, request: BehaviorRepairRegressionRequest) -> BehaviorRepairOutcome:
        repair, state = request.repair, request.state
        revision = state.behavior_review.repair.current_candidate_revision
        if revision is None:
            raise ValueError("behavior repair regression requires an accepted candidate")
        artifact = repair.adapter.materialise_final_test(
            FinalTestMaterialisationRequest(state.model, state.fragments, revision)
        )
        candidate = self.candidates.materialise(
            BehaviorRepairCandidateRequest(artifact, repair.repository_root, state.model.test_path)
        )
        try:
            result = self.regression.run(
                DeterministicRegressionRequest(
                    candidate.project_root,
                    state.regression.command,
                    artifact.canonical_test_identity,
                    repair.prior_completed_test_nodes,
                    repair.include_accepted_regression_suite,
                )
            )
        finally:
            self.candidates.cleanup(candidate)
        progress = replace(
            state.behavior_review.repair,
            current_candidate_revision=candidate.candidate_revision,
            regression=result.state(state.regression.command),
        )
        updated = replace(
            state,
            behavior_review=replace(state.behavior_review, repair=progress),
            candidate_chain_revision=candidate.candidate_revision,
            regression=result.state(state.regression.command),
        )
        self.state_store.save(updated)
        status = "behavior_repair_regression_clear" if result.status == REGRESSION_CLEAR else result.status
        return BehaviorRepairOutcome(updated, status, request.developer_submissions)

    def promote(self, request: BehaviorRepairRequest) -> BehaviorRepairOutcome:
        state = request.state
        candidate = state.behavior_review.repair.current_candidate_revision
        if candidate is None or state.regression.status != REGRESSION_CLEAR:
            raise ValueError("behavior repair promotion requires a regression-clear candidate")
        _promote_canonical_revision(request, candidate)
        promoted = replace(state, development_base_revision=candidate, candidate_chain_revision=candidate)
        self.state_store.save(promoted)
        return BehaviorRepairOutcome(promoted, "behavior_repair_promoted")


def _progress_after_submission(
    progress: BehaviorRepairProgress,
    work_unit_id: str,
    revision: str | None,
    evidence_location: str | None,
    error: str | None,
) -> BehaviorRepairProgress:
    evidence = tuple(item for item in (evidence_location, error) if item)
    return BehaviorRepairProgress(
        progress.attempts + 1,
        progress.current_candidate_revision,
        BehaviorRepairExecution(work_unit_id, revision, evidence),
        progress.regression,
    )


def _working_binding(request: BehaviorRepairRequest, expected_revision: str) -> RepositoryBinding:
    if request.revision_lifecycle is None or request.revision_binding_request is None:
        return request.repository_binding.with_base_sha(expected_revision)
    binding = request.revision_lifecycle.binding(request.revision_binding_request)
    if binding.base_sha != expected_revision:
        raise ValueError("managed working ref does not match the active behavior-repair revision")
    return binding


def _advance_working_revision(
    request: BehaviorRepairRequest,
    candidate_revision: str,
    evidence_ref: str | None,
) -> None:
    if request.revision_lifecycle is None or request.revision_binding_request is None:
        return
    current = request.revision_lifecycle.recover(RevisionRecoveryRequest(request.revision_binding_request.scenario_id))
    if current.working_revision == candidate_revision:
        return
    evidence = tuple(item for item in (evidence_ref,) if item)
    request.revision_lifecycle.advance(
        RevisionTransitionRequest(
            current, candidate_revision, RevisionTransitionKind.REGRESSION_REPAIR_ACCEPTED.value, evidence
        )
    )


def _promote_canonical_revision(request: BehaviorRepairRequest, candidate_revision: str) -> None:
    if request.revision_lifecycle is None or request.revision_binding_request is None:
        return
    current = request.revision_lifecycle.recover(RevisionRecoveryRequest(request.revision_binding_request.scenario_id))
    if current.canonical_development_base == candidate_revision:
        return
    request.revision_lifecycle.promote(
        RevisionTransitionRequest(
            current, candidate_revision, RevisionTransitionKind.REGRESSION_CLEAR.value, ()
        )
    )
