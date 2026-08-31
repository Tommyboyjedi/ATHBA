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
            if changed != (request.test_path,):
                raise ValueError("frontier materialisation changed paths outside the authorised test path")
            _git(worktree, "-c", "user.name=ATHBA", "-c", "user.email=athba@example.test", "commit", "--no-verify", "-m", "ATHBA materialise strict TDD frontier")
            revision = _git(worktree, "rev-parse", "HEAD").strip()
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


@dataclass(frozen=True)
class StrictMicrocycleRequest:
    project_id: str
    production_path: str
    repository_root: Path
    repository_binding: RepositoryBinding
    initial_state: MicrocycleState


@dataclass(frozen=True)
class StrictMicrocycleDependencies:
    state_store: MicrocycleStateStore
    candidate_repository: FrontierCandidateRepository
    execution_gateway: WorkUnitExecutionGateway
    adapters: LanguageAdapterCatalog
    developer_factory: DeveloperFrontierWorkUnitFactory = DeveloperFrontierWorkUnitFactory()


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
        self.developer_factory = dependencies.developer_factory

    async def run(self, request: StrictMicrocycleRequest) -> StrictMicrocycleOutcome:
        state = self._load(request)
        adapter = self.adapters.for_language(state.model.language_id)
        submitted = 0
        while state.completion.status == "pending":
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
            if state.frontier.index == len(state.fragments) - 1:
                state = replace(state, completion=ScenarioCompletion("complete", state.candidate_chain_revision))
                self.state_store.save(state)
                return StrictMicrocycleOutcome(state, "complete", submitted)
            state = _advance(state, state.candidate_chain_revision or state.development_base_revision)
            self.state_store.save(state)
        return StrictMicrocycleOutcome(state, "complete", submitted)

    def _load(self, request: StrictMicrocycleRequest) -> MicrocycleState:
        stored = self.state_store.load(request.initial_state.scenario_draft.scenario_id)
        state = stored or request.initial_state
        if state.scenario_draft != request.initial_state.scenario_draft:
            raise ValueError("stored microcycle does not match the approved scenario")
        if request.repository_binding.base_sha != state.development_base_revision:
            raise ValueError("repository binding must start at the approved development base")
        if stored is None:
            self.state_store.save(state)
        return state

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
        finally:
            self.candidates.cleanup(candidate)
        state = _record_execution(state, base, assessment)
        if assessment.outcome == BoundaryOutcome.GREEN.value:
            state = replace(state, candidate_chain_revision=candidate.candidate_revision)
        elif assessment.outcome in _VALID_RED_OUTCOMES:
            state = replace(state, current_accepted_red_revision=candidate.candidate_revision)
        self.state_store.save(state)
        return StrictMicrocycleOutcome(state, "green" if assessment.outcome == BoundaryOutcome.GREEN.value else assessment.outcome)

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
        result = await self.gateway.execute(self.developer_factory.build(packet), request.repository_binding.with_base_sha(red))
        state = _record_developer(state, red, result)
        self.state_store.save(state)
        if not result.accepted or result.accepted_revision is None:
            return state, StrictMicrocycleOutcome(state, "developer_candidate_rejected", 1)
        state = replace(state, candidate_chain_revision=result.accepted_revision, current_accepted_red_revision=None)
        if state.frontier.index == len(state.fragments) - 1:
            state = replace(state, completion=ScenarioCompletion("complete", result.accepted_revision))
        else:
            state = _advance(state, result.accepted_revision)
        self.state_store.save(state)
        return state, StrictMicrocycleOutcome(state, "advanced", 1)


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
        candidate_chain_revision=base,
    )
