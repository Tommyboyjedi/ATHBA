"""Deterministic strict-TDD frontier materialisation and narrow GREEN execution."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from core.development.behavior_completion import REPAIR_REQUIRED, BehaviorCompletionCommand, BehaviorCompletionService
from core.development.behavior_repair import BehaviorRepairRequest, BehaviorRepairService
from core.development.deterministic_regression import (
    DeterministicRegressionRequest,
    DeterministicRegressionService,
    ACCUMULATED_REGRESSION,
    REGRESSION_CLEAR,
)
from core.development.microcycle_domain import (
    MAX_MICROCYCLE_ATTEMPTS,
    BoundaryAssessment,
    BoundaryClassificationRequest,
    BoundaryOutcome,
    DeveloperAttempt,
    FrontierAttemptCounts,
    FrontierExecutionRequest,
    FrontierMaterialisationRequest,
    LanguageAdapterCatalog,
    LanguageTestAdapter,
    MaterialisedTestArtifact,
    MicrocycleState,
    RegressionState,
    ScenarioCompletion,
    ScenarioFrontier,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult


@dataclass(frozen=True)
class FrontierCandidate:
    artifact: MaterialisedTestArtifact
    candidate_revision: str
    project_root: Path
    repository_root: Path


@dataclass(frozen=True)
class FrontierCandidateRequest:
    artifact: MaterialisedTestArtifact
    repository_root: Path
    test_path: str


class FrontierCandidateRepository(Protocol):
    def materialise(self, request: FrontierCandidateRequest) -> FrontierCandidate: ...
    def cleanup(self, candidate: FrontierCandidate) -> None: ...


class MicrocycleStateStore(Protocol):
    def load(self, scenario_id: str) -> MicrocycleState | None: ...
    def save(self, state: MicrocycleState) -> object: ...


class GitFrontierMaterialiser:
    """Writes one generated test artifact into a detached, disposable Git worktree."""

    def materialise(self, request: FrontierCandidateRequest) -> FrontierCandidate:
        root = request.repository_root.resolve()
        test_path = _safe_test_path(root, request.test_path)
        worktree = Path(tempfile.mkdtemp(prefix="athba-frontier-")).resolve()
        worktree.rmdir()
        _git(root, "worktree", "add", "--detach", str(worktree), request.artifact.base_revision)
        try:
            target = _safe_test_path(worktree, request.test_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(request.artifact.complete_source, encoding="utf-8")
            _git(worktree, "add", "--", request.test_path)
            changed = tuple(line for line in _git(worktree, "diff", "--cached", "--name-only").splitlines() if line)
            if changed not in {(request.test_path,), ()}:
                raise ValueError("frontier materialisation changed paths outside the authorised test path")
            if changed:
                _git(worktree, "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "--no-verify", "-m", "ATHBA materialise strict TDD frontier")
                revision = _git(worktree, "rev-parse", "HEAD").strip()
            else:
                revision = request.artifact.base_revision
            return FrontierCandidate(replace(request.artifact, candidate_revision=revision), revision, worktree, root)
        except Exception:
            _discard_worktree(root, worktree)
            raise

    def cleanup(self, candidate: FrontierCandidate) -> None:
        _discard_worktree(candidate.repository_root, candidate.project_root)


@dataclass(frozen=True)
class DeveloperFrontierRequest:
    project_id: str
    production_path: str
    artifact: MaterialisedTestArtifact
    assessment: BoundaryAssessment
    accepted_red_revision: str
    development_base_revision: str
    attempt_number: int


class DeveloperFrontierWorkUnitFactory:
    """Creates a Developer packet containing only one accepted frontier."""

    def build(self, request: DeveloperFrontierRequest) -> DevelopmentWorkUnit:
        identifier = f"{request.artifact.scenario_id}--frontier-{request.artifact.frontier_index}--developer-{request.attempt_number}"
        objective = json.dumps(
            {
                "role": "Developer",
                "task": "Make this active frontier pass using the smallest production change required.",
                "materialised_active_frontier_test": request.artifact.complete_source,
                "boundary_diagnostic": request.assessment.diagnostic.to_dict(),
                "production_path": request.production_path,
                "accepted_red_revision": request.accepted_red_revision,
                "development_base_context": request.development_base_revision,
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


class RegressionRepairWorkUnitFactory:
    """Limits Developer repair context to the current frontier and new regressions."""

    def build(self, request: DeveloperFrontierRequest, failing_nodes: tuple[str, ...]) -> DevelopmentWorkUnit:
        identifier = f"{request.artifact.scenario_id}--frontier-{request.artifact.frontier_index}--regression-repair-{request.attempt_number}"
        objective = json.dumps({
            "role": "Developer",
            "task": "Repair only newly regressed prior tests while preserving the current frontier.",
            "current_frontier_test": request.artifact.complete_source,
            "newly_failing_prior_tests": failing_nodes,
            "production_path": request.production_path,
        }, sort_keys=True)
        commands = [[sys.executable, "-m", "pytest", "-q", request.artifact.canonical_test_identity]]
        commands.extend([[sys.executable, "-m", "pytest", "-q", node] for node in failing_nodes])
        return DevelopmentWorkUnit(
            id=identifier,
            project_id=request.project_id,
            parent_ticket_id=request.artifact.scenario_id,
            objective=objective,
            allowed_paths=[request.production_path],
            acceptance=AcceptanceContract(commands, required_artifacts=[request.production_path]),
            max_implementation_attempts=1,
            change_key=identifier,
            status=WorkUnitStatus.READY,
        )


@dataclass(frozen=True)
class StrictMicrocycleRequest:
    project_id: str
    production_path: str
    repository_root: Path
    repository_binding: RepositoryBinding
    initial_state: MicrocycleState
    prior_completed_test_nodes: tuple[str, ...] = ()
    include_accepted_regression_suite: bool = True


@dataclass(frozen=True)
class StrictMicrocycleDependencies:
    state_store: MicrocycleStateStore
    candidate_repository: FrontierCandidateRepository
    execution_gateway: WorkUnitExecutionGateway
    adapters: LanguageAdapterCatalog
    regression: DeterministicRegressionService
    developer_factory: DeveloperFrontierWorkUnitFactory = DeveloperFrontierWorkUnitFactory()
    regression_repair_factory: RegressionRepairWorkUnitFactory = RegressionRepairWorkUnitFactory()
    behavior_completion: BehaviorCompletionService | None = None
    behavior_repair: BehaviorRepairService | None = None


@dataclass(frozen=True)
class RegressionRepairContext:
    request: StrictMicrocycleRequest
    state: MicrocycleState
    adapter: LanguageTestAdapter


@dataclass(frozen=True)
class RegressionRepairDependencies:
    state_store: MicrocycleStateStore
    candidates: FrontierCandidateRepository
    gateway: WorkUnitExecutionGateway
    regression: DeterministicRegressionService
    factory: RegressionRepairWorkUnitFactory


class RegressionRepairService:
    """Runs a bounded repair and immediately rechecks the complete deterministic suite."""

    def __init__(self, dependencies: RegressionRepairDependencies):
        self.state_store = dependencies.state_store
        self.candidates = dependencies.candidates
        self.gateway = dependencies.gateway
        self.regression = dependencies.regression
        self.factory = dependencies.factory

    async def repair(self, context: RegressionRepairContext) -> tuple[MicrocycleState, StrictMicrocycleOutcome]:
        request, state, adapter = context.request, context.state, context.adapter
        failing = state.regression.failing_prior_test_nodes
        if not failing:
            return state, StrictMicrocycleOutcome(state, ACCUMULATED_REGRESSION)
        if state.retry_counts.regression >= MAX_MICROCYCLE_ATTEMPTS:
            return state, StrictMicrocycleOutcome(state, "regression_repair_attempts_exhausted")
        base = state.candidate_chain_revision or state.development_base_revision
        artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, base))
        packet = DeveloperFrontierRequest(request.project_id, request.production_path, artifact, state.boundary_evidence[-1], base, state.development_base_revision, state.retry_counts.regression + 1)
        result = await self.gateway.execute(self.factory.build(packet, failing), request.repository_binding.with_base_sha(base))
        state = replace(state, retry_counts=replace(state.retry_counts, regression=state.retry_counts.regression + 1))
        if not result.accepted or result.accepted_revision is None:
            self.state_store.save(state)
            return state, StrictMicrocycleOutcome(state, "regression_repair_rejected", 1)
        candidate = self.candidates.materialise(FrontierCandidateRequest(replace(artifact, base_revision=result.accepted_revision), request.repository_root, state.model.test_path))
        try:
            regression = self.regression.run(DeterministicRegressionRequest(candidate.project_root, state.regression.command, artifact.canonical_test_identity, request.prior_completed_test_nodes, request.include_accepted_regression_suite))
        finally:
            self.candidates.cleanup(candidate)
        state = replace(state, regression=regression.state(state.regression.command))
        if regression.status == REGRESSION_CLEAR:
            state = replace(state, candidate_chain_revision=candidate.candidate_revision, development_base_revision=candidate.candidate_revision)
        self.state_store.save(state)
        return state, StrictMicrocycleOutcome(state, "green" if regression.status == REGRESSION_CLEAR else regression.status, 1)


@dataclass(frozen=True)
class StrictMicrocycleOutcome:
    state: MicrocycleState
    status: str
    developer_submissions: int = 0


@dataclass(frozen=True)
class FrontierExecutionContext:
    request: StrictMicrocycleRequest
    state: MicrocycleState
    adapter: LanguageTestAdapter


@dataclass(frozen=True)
class DeveloperExecutionContext:
    request: StrictMicrocycleRequest
    state: MicrocycleState


class StrictMicrocycleService:
    """Runs only complete frontiers, stopping before an untrusted transition."""

    def __init__(self, dependencies: StrictMicrocycleDependencies):
        self.state_store = dependencies.state_store
        self.candidates = dependencies.candidate_repository
        self.gateway = dependencies.execution_gateway
        self.adapters = dependencies.adapters
        self.regression = dependencies.regression
        self.developer_factory = dependencies.developer_factory
        self.regression_repair_factory = dependencies.regression_repair_factory
        self.repair_service = RegressionRepairService(
            RegressionRepairDependencies(self.state_store, self.candidates, self.gateway, self.regression, self.regression_repair_factory)
        )
        self.behavior_completion = dependencies.behavior_completion
        self.behavior_repair = dependencies.behavior_repair

    async def run(self, request: StrictMicrocycleRequest) -> StrictMicrocycleOutcome:
        state = _load_state(self.state_store, self.adapters, request)
        adapter = self.adapters.for_language(state.model.language_id)
        submitted = 0
        while True:
            if state.completion.status == "behavior_complete":
                return StrictMicrocycleOutcome(state, "behavior_complete", submitted)
            if state.completion.status == "scenario_complete":
                routed = await _route_completed_behavior(
                    CompletedBehaviorRouteRequest(request, state, adapter, self.behavior_completion, self.behavior_repair, self.repair_service, self.state_store)
                )
                state, outcome = routed.state, routed.outcome
                submitted += outcome.developer_submissions
                if outcome.status == "continue":
                    continue
                return StrictMicrocycleOutcome(state, outcome.status, submitted)
            if state.regression.status == REGRESSION_CLEAR:
                if state.frontier.index == len(state.fragments) - 1:
                    state = replace(state, completion=ScenarioCompletion("scenario_complete", state.development_base_revision))
                    self.state_store.save(state)
                    continue
                state = _advance(state, state.development_base_revision)
                self.state_store.save(state)
                continue
            if state.regression.status == ACCUMULATED_REGRESSION:
                state, repair = await self.repair_service.repair(RegressionRepairContext(request, state, adapter))
                submitted += repair.developer_submissions
                if repair.status != "green":
                    return StrictMicrocycleOutcome(state, repair.status, submitted)
                continue
            if state.current_accepted_red_revision is not None:
                state, result = await self._developer(DeveloperExecutionContext(request, state))
                submitted += result.developer_submissions
                if result.status != "advanced":
                    return StrictMicrocycleOutcome(state, result.status, submitted)
                continue
            outcome = self._execute_frontier(FrontierExecutionContext(request, state, adapter))
            state = outcome.state
            if state.current_accepted_red_revision is not None:
                continue
            if outcome.status != "green":
                return StrictMicrocycleOutcome(state, outcome.status, submitted)

    def _execute_frontier(self, context: FrontierExecutionContext) -> StrictMicrocycleOutcome:
        request, state, adapter = context.request, context.state, context.adapter
        base = state.candidate_chain_revision or state.development_base_revision
        counts = _counts_for(state, base)
        if counts.executions >= MAX_MICROCYCLE_ATTEMPTS:
            return StrictMicrocycleOutcome(state, "frontier_execution_attempts_exhausted")
        artifact = adapter.materialise_frontier(FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, base))
        candidate = self.candidates.materialise(FrontierCandidateRequest(artifact, request.repository_root, state.model.test_path))
        try:
            diagnostic = adapter.execute_frontier(FrontierExecutionRequest(candidate.artifact, str(candidate.project_root), state.model.test_path))
            prior = BoundaryOutcome.GREEN.value if state.frontier.index else None
            assessment = adapter.classify_boundary(BoundaryClassificationRequest(diagnostic, candidate.artifact, state.fragments[state.frontier.index], prior))
            state = _record_execution(state, base, assessment)
            if assessment.outcome == BoundaryOutcome.GREEN.value:
                regression = self.regression.run(
                    DeterministicRegressionRequest(
                        candidate.project_root,
                        state.regression.command,
                        candidate.artifact.canonical_test_identity,
                        request.prior_completed_test_nodes,
                        request.include_accepted_regression_suite,
                    )
                )
                state = replace(state, regression=regression.state(state.regression.command))
                if regression.status == REGRESSION_CLEAR:
                    state = replace(
                        state,
                        candidate_chain_revision=candidate.candidate_revision,
                        development_base_revision=candidate.candidate_revision,
                    )
                self.state_store.save(state)
                return StrictMicrocycleOutcome(state, "green" if regression.status == REGRESSION_CLEAR else regression.status)
            if assessment.outcome in _VALID_RED_OUTCOMES:
                state = replace(state, current_accepted_red_revision=candidate.candidate_revision)
            self.state_store.save(state)
            return StrictMicrocycleOutcome(state, assessment.outcome)
        finally:
            self.candidates.cleanup(candidate)

    async def _developer(self, context: DeveloperExecutionContext) -> tuple[MicrocycleState, StrictMicrocycleOutcome]:
        request, state = context.request, context.state
        red = state.current_accepted_red_revision
        if red is None:
            raise ValueError("Developer requires an accepted RED revision")
        counts = _counts_for(state, red)
        if counts.developer_attempts >= MAX_MICROCYCLE_ATTEMPTS:
            return state, StrictMicrocycleOutcome(state, "developer_attempts_exhausted")
        assessment = state.boundary_evidence[-1]
        artifact = self.adapters.for_language(state.model.language_id).materialise_frontier(
            FrontierMaterialisationRequest(state.model, state.fragments, state.frontier, red)
        )
        packet = DeveloperFrontierRequest(
            request.project_id, request.production_path, artifact, assessment, red,
            state.candidate_chain_revision or state.development_base_revision, counts.developer_attempts + 1,
        )
        work_unit = self.developer_factory.build(packet)
        result = await self.gateway.execute(work_unit, request.repository_binding.with_base_sha(red))
        if result.work_unit_id != work_unit.id:
            raise ValueError("stale Rack AI packet does not match the active Developer frontier")
        state = _record_developer(state, red, result)
        if not result.accepted or result.accepted_revision is None:
            self.state_store.save(state)
            return state, StrictMicrocycleOutcome(state, "developer_candidate_rejected", 1)
        state = replace(state, candidate_chain_revision=result.accepted_revision, current_accepted_red_revision=None)
        self.state_store.save(state)
        return state, StrictMicrocycleOutcome(state, "advanced", 1)




@dataclass(frozen=True)
class CompletedBehaviorRoute:
    state: MicrocycleState
    outcome: StrictMicrocycleOutcome


@dataclass(frozen=True)
class CompletedBehaviorRouteRequest:
    microcycle: StrictMicrocycleRequest
    state: MicrocycleState
    adapter: LanguageTestAdapter
    completion: BehaviorCompletionService | None
    behavior_repair: BehaviorRepairService | None
    regression_repair: RegressionRepairService
    state_store: MicrocycleStateStore


async def _route_completed_behavior(request: CompletedBehaviorRouteRequest) -> CompletedBehaviorRoute:
    state = request.state
    review = state.behavior_review
    progress = review.repair
    if request.behavior_repair is not None and progress.current_candidate_revision:
        if state.regression.status == ACCUMULATED_REGRESSION:
            state, repair = await request.regression_repair.repair(
                RegressionRepairContext(request.microcycle, state, request.adapter)
            )
            if repair.status != "green":
                return CompletedBehaviorRoute(state, repair)
            state = _record_repair_regression(state)
            request.state_store.save(state)
            return CompletedBehaviorRoute(state, StrictMicrocycleOutcome(state, "continue", repair.developer_submissions))
        if progress.regression is not None and progress.regression.status != REGRESSION_CLEAR:
            result = await request.behavior_repair.repair(
                _behavior_repair_request(request.microcycle, state, request.adapter)
            )
            status = "continue" if result.status == "behavior_repair_regression_clear" else result.status
            return CompletedBehaviorRoute(result.state, StrictMicrocycleOutcome(result.state, status, result.developer_submissions))
    reviewed = await _complete_behavior(request.completion, request.state_store, state, 0)
    if reviewed.status != REPAIR_REQUIRED or request.behavior_repair is None:
        return CompletedBehaviorRoute(reviewed.state, reviewed)
    repaired = await request.behavior_repair.repair(
        _behavior_repair_request(request.microcycle, reviewed.state, request.adapter)
    )
    status = "continue" if repaired.status == "behavior_repair_regression_clear" else repaired.status
    return CompletedBehaviorRoute(repaired.state, StrictMicrocycleOutcome(repaired.state, status, repaired.developer_submissions))


def _behavior_repair_request(
    request: StrictMicrocycleRequest,
    state: MicrocycleState,
    adapter: LanguageTestAdapter,
) -> BehaviorRepairRequest:
    return BehaviorRepairRequest(
        request.project_id,
        request.production_path,
        request.repository_root,
        request.repository_binding,
        state,
        adapter,
        request.prior_completed_test_nodes,
        request.include_accepted_regression_suite,
    )


def _record_repair_regression(state: MicrocycleState) -> MicrocycleState:
    repair = replace(
        state.behavior_review.repair,
        current_candidate_revision=state.development_base_revision,
        regression=state.regression,
    )
    return replace(state, behavior_review=replace(state.behavior_review, repair=repair))


async def _complete_behavior(
    behavior_completion: BehaviorCompletionService | None,
    state_store: MicrocycleStateStore,
    state: MicrocycleState,
    submitted: int,
) -> StrictMicrocycleOutcome:
    if behavior_completion is None:
        return StrictMicrocycleOutcome(state, "scenario_complete", submitted)
    state = await behavior_completion.complete(BehaviorCompletionCommand(state, persist=state_store.save))
    state_store.save(state)
    status = "behavior_complete" if state.completion.status == "behavior_complete" else state.behavior_review.verdict
    return StrictMicrocycleOutcome(state, status, submitted)


def _load_state(
    state_store: MicrocycleStateStore,
    adapters: LanguageAdapterCatalog,
    request: StrictMicrocycleRequest,
) -> MicrocycleState:
    stored = state_store.load(request.initial_state.scenario_draft.scenario_id)
    state = stored or request.initial_state
    if state.scenario_draft != request.initial_state.scenario_draft:
        raise ValueError("stored microcycle does not match the approved scenario")
    adapter = adapters.for_language(state.model.language_id)
    if adapter.descriptor.adapter_version != state.model.adapter_version:
        raise ValueError("stored microcycle adapter version does not match the registered adapter")
    if stored is None and request.repository_binding.base_sha != state.development_base_revision:
        raise ValueError("repository binding must start at the approved development base")
    if stored is None:
        state_store.save(state)
    return state


_VALID_RED_OUTCOMES = {
    BoundaryOutcome.VALID_MISSING_CAPABILITY_RED.value,
    BoundaryOutcome.VALID_BEHAVIORAL_RED.value,
}


def _safe_test_path(root: Path, test_path: str) -> Path:
    candidate = Path(test_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("frontier test path is unsafe")
    resolved = (root / candidate).resolve()
    if root not in resolved.parents:
        raise ValueError("frontier test path escapes repository root")
    return resolved


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise ValueError((completed.stderr or completed.stdout).strip())
    return completed.stdout


def _discard_worktree(repository_root: Path, worktree: Path) -> None:
    root = repository_root.resolve()
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=root, text=True, capture_output=True, check=False)
    if worktree.exists():
        shutil.rmtree(worktree, ignore_errors=True)


def _counts_for(state: MicrocycleState, base: str) -> FrontierAttemptCounts:
    for item in state.frontier_attempt_counts:
        if item.frontier_index == state.frontier.index and item.base_revision == base:
            return item
    return FrontierAttemptCounts(state.frontier.index, base)


def _replace_counts(state: MicrocycleState, value: FrontierAttemptCounts) -> MicrocycleState:
    kept = tuple(item for item in state.frontier_attempt_counts if (item.frontier_index, item.base_revision) != (value.frontier_index, value.base_revision))
    return replace(state, frontier_attempt_counts=(*kept, value))


def _record_execution(state: MicrocycleState, base: str, assessment: BoundaryAssessment) -> MicrocycleState:
    counts = _counts_for(state, base)
    return _replace_counts(
        replace(state, boundary_evidence=(*state.boundary_evidence, assessment)),
        replace(counts, executions=counts.executions + 1),
    )


def _record_developer(state: MicrocycleState, base: str, result: WorkUnitExecutionResult) -> MicrocycleState:
    counts = _counts_for(state, base)
    attempt = DeveloperAttempt(
        counts.developer_attempts + 1, state.frontier.index, base, result.accepted_revision,
        tuple(item for item in (result.evidence_location, result.error) if item),
    )
    return _replace_counts(
        replace(state, developer_attempts=(*state.developer_attempts, attempt)),
        replace(counts, developer_attempts=counts.developer_attempts + 1),
    )


def _advance(state: MicrocycleState, base: str) -> MicrocycleState:
    index = state.frontier.index + 1
    ids = tuple(item.fragment_id for item in state.fragments[:index + 1])
    return replace(
        state,
        frontier=ScenarioFrontier(state.scenario_draft.scenario_id, index, ids[-1], ids),
        current_accepted_red_revision=None,
        retry_counts=replace(state.retry_counts, developer=0, frontier_execution=0),
        regression=RegressionState("pending", state.regression.command),
        candidate_chain_revision=base,
    )
