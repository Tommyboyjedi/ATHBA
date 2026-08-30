"""Compatibility TDD coordination over shared phase execution semantics."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Protocol

from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.progression import ExecutionAttemptRecord
from core.development.tdd_phase_execution import PhaseExecutionRequest, TddPhaseExecutor
from core.development.tdd_progression import (
    TddBehavior,
    TddBehaviorProgress,
    TddPhase,
    TddSnapshot,
    green_work_unit_id,
    red_work_unit_id,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway


@dataclass(frozen=True)
class TddCoordinationResult:
    completed_behavior_ids: list[str]
    attempts: list[ExecutionAttemptRecord]
    current_binding: RepositoryBinding
    final_revision: str | None
    behaviors: dict[str, TddBehaviorProgress]
    blocked_behavior_id: str | None = None
    blocked_phase: str | None = None
    blocked_reason: str | None = None


class TddStateRepository(Protocol):
    def load(self, project_id: str) -> TddSnapshot | None:
        ...

    def save(self, snapshot: TddSnapshot):
        ...


class TesterWorkUnitFactory:
    """Build RED-phase work units without owning physical execution."""

    def build(self, behavior: TddBehavior) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=red_work_unit_id(behavior.id),
            project_id=behavior.project_id,
            parent_ticket_id=behavior.parent_ticket_id,
            objective=behavior.red_objective,
            allowed_paths=[behavior.test_path],
            acceptance=AcceptanceContract(
                commands=[list(command) for command in behavior.red_acceptance_commands],
                required_artifacts=[behavior.test_path],
            ),
            status=WorkUnitStatus.READY,
        )


class DeveloperWorkUnitFactory:
    """Build GREEN-phase work units without owning physical execution."""

    def build(self, behavior: TddBehavior) -> DevelopmentWorkUnit:
        return DevelopmentWorkUnit(
            id=green_work_unit_id(behavior.id),
            project_id=behavior.project_id,
            parent_ticket_id=behavior.parent_ticket_id,
            objective=behavior.green_objective,
            allowed_paths=[behavior.production_path],
            acceptance=AcceptanceContract(
                commands=[list(command) for command in behavior.green_acceptance_commands],
                required_artifacts=[behavior.production_path],
            ),
            status=WorkUnitStatus.READY,
        )


@dataclass(frozen=True)
class TddCoordinatorDependencies:
    gateway: WorkUnitExecutionGateway
    repository_binding: RepositoryBinding
    state_repo: TddStateRepository
    tester_factory: TesterWorkUnitFactory
    developer_factory: DeveloperWorkUnitFactory


@dataclass(frozen=True)
class TddCoordinationContext:
    project_id: str
    current_binding: RepositoryBinding
    attempts: list[ExecutionAttemptRecord]
    completed_behavior_ids: list[str]
    behaviors: dict[str, TddBehaviorProgress]


class TddCoordinator:
    """Run one predefined RED->GREEN cycle per behavior in order."""

    def __init__(
        self,
        gateway: WorkUnitExecutionGateway,
        repository_binding: RepositoryBinding,
        *legacy: object,
    ):
        self.dependencies = _coordinator_dependencies(
            gateway,
            repository_binding,
            legacy,
        )

    async def run(self, behaviors: Iterable[TddBehavior]) -> TddCoordinationResult:
        return await _run_behaviors(self.dependencies, list(behaviors))


def _coordinator_dependencies(
    gateway: WorkUnitExecutionGateway,
    repository_binding: RepositoryBinding,
    legacy: tuple[object, ...],
) -> TddCoordinatorDependencies:
    if len(legacy) > 3:
        raise TypeError(
            "TddCoordinator accepts gateway, repository_binding, and up to three legacy collaborators"
        )
    return TddCoordinatorDependencies(
        gateway=gateway,
        repository_binding=repository_binding,
        state_repo=legacy[0] if len(legacy) >= 1 else TddStateRepo(),
        tester_factory=legacy[1] if len(legacy) >= 2 else TesterWorkUnitFactory(),
        developer_factory=legacy[2] if len(legacy) >= 3 else DeveloperWorkUnitFactory(),
    )


async def _run_behaviors(
    deps: TddCoordinatorDependencies,
    ordered: list[TddBehavior],
) -> TddCoordinationResult:
    if not ordered:
        return TddCoordinationResult(
            completed_behavior_ids=[],
            attempts=[],
            current_binding=deps.repository_binding,
            final_revision=deps.repository_binding.base_sha,
            behaviors={},
        )
    project_id = ordered[0].project_id
    snapshot = deps.state_repo.load(project_id)
    if snapshot is not None and snapshot.blocked_behavior_id is not None:
        return _result_from_snapshot(snapshot)
    context = _coordination_context(deps.repository_binding, ordered, snapshot)
    executor = TddPhaseExecutor(deps.gateway)
    for behavior in ordered:
        context, blocked = await _run_behavior(deps, executor, context, behavior)
        if blocked is not None:
            _save_result(deps.state_repo, project_id, blocked)
            return blocked
    result = _result_from_context(context)
    _save_result(deps.state_repo, project_id, result)
    return result


async def _run_behavior(
    deps: TddCoordinatorDependencies,
    executor: TddPhaseExecutor,
    context: TddCoordinationContext,
    behavior: TddBehavior,
) -> tuple[TddCoordinationContext, TddCoordinationResult | None]:
    if behavior.id in context.completed_behavior_ids:
        return context, None
    progress = context.behaviors[behavior.id]
    if progress.status == "completed":
        return _with_completed_behavior(context, behavior.id), None
    context, blocked = await _run_red_phase(deps, executor, context, behavior, progress)
    if blocked is not None:
        return context, blocked
    progress = context.behaviors[behavior.id]
    return await _run_green_phase(deps, executor, context, behavior, progress)


async def _run_red_phase(
    deps: TddCoordinatorDependencies,
    executor: TddPhaseExecutor,
    context: TddCoordinationContext,
    behavior: TddBehavior,
    progress: TddBehaviorProgress,
) -> tuple[TddCoordinationContext, TddCoordinationResult | None]:
    if progress.red_phase.accepted_revision is not None:
        binding = context.current_binding.with_base_sha(progress.red_phase.accepted_revision)
        return replace(context, current_binding=binding), None
    work_unit = deps.tester_factory.build(behavior)
    outcome = await executor.execute(
        PhaseExecutionRequest(TddPhase.RED, work_unit, context.current_binding)
    )
    updated = replace(
        progress,
        current_phase=TddPhase.GREEN.value if outcome.accepted else TddPhase.RED.value,
        status="red_accepted" if outcome.accepted else "blocked",
        red_phase=outcome.phase_state,
    )
    context = _with_progress(_with_attempt(context, outcome.attempt), behavior.id, updated)
    if not outcome.accepted:
        return context, _blocked_result(
            context,
            behavior.id,
            TddPhase.RED.value,
            outcome.blocked_reason,
        )
    binding = context.current_binding.with_base_sha(outcome.phase_state.accepted_revision)
    context = replace(context, current_binding=binding)
    _save_context(deps.state_repo, context)
    return context, None


async def _run_green_phase(
    deps: TddCoordinatorDependencies,
    executor: TddPhaseExecutor,
    context: TddCoordinationContext,
    behavior: TddBehavior,
    progress: TddBehaviorProgress,
) -> tuple[TddCoordinationContext, TddCoordinationResult | None]:
    if progress.green_phase.accepted_revision is not None:
        binding = context.current_binding.with_base_sha(progress.green_phase.accepted_revision)
        context = replace(context, current_binding=binding)
        return _with_completed_behavior(context, behavior.id), None
    work_unit = deps.developer_factory.build(behavior)
    outcome = await executor.execute(
        PhaseExecutionRequest(TddPhase.GREEN, work_unit, context.current_binding)
    )
    updated = replace(
        progress,
        current_phase=TddPhase.COMPLETE.value if outcome.accepted else TddPhase.GREEN.value,
        status="completed" if outcome.accepted else "blocked",
        green_phase=outcome.phase_state,
    )
    context = _with_progress(_with_attempt(context, outcome.attempt), behavior.id, updated)
    if not outcome.accepted:
        return context, _blocked_result(
            context,
            behavior.id,
            TddPhase.GREEN.value,
            outcome.blocked_reason,
        )
    binding = context.current_binding.with_base_sha(outcome.phase_state.accepted_revision)
    context = _with_completed_behavior(replace(context, current_binding=binding), behavior.id)
    _save_context(deps.state_repo, context)
    return context, None


def _coordination_context(
    binding: RepositoryBinding,
    ordered: list[TddBehavior],
    snapshot: TddSnapshot | None,
) -> TddCoordinationContext:
    behaviors = dict(snapshot.behaviors) if snapshot else {}
    for behavior in ordered:
        behaviors.setdefault(behavior.id, TddBehaviorProgress.from_behavior(behavior))
    return TddCoordinationContext(
        project_id=ordered[0].project_id,
        current_binding=snapshot.repository_binding if snapshot else binding,
        attempts=list(snapshot.attempts) if snapshot else [],
        completed_behavior_ids=list(snapshot.completed_behavior_ids) if snapshot else [],
        behaviors=behaviors,
    )


def _with_attempt(
    context: TddCoordinationContext,
    attempt: ExecutionAttemptRecord | None,
) -> TddCoordinationContext:
    if attempt is None:
        return context
    return replace(context, attempts=[*context.attempts, attempt])


def _with_progress(
    context: TddCoordinationContext,
    behavior_id: str,
    progress: TddBehaviorProgress,
) -> TddCoordinationContext:
    return replace(context, behaviors={**context.behaviors, behavior_id: progress})


def _with_completed_behavior(
    context: TddCoordinationContext,
    behavior_id: str,
) -> TddCoordinationContext:
    if behavior_id in context.completed_behavior_ids:
        return context
    completed = [*context.completed_behavior_ids, behavior_id]
    return replace(context, completed_behavior_ids=completed)


def _blocked_result(
    context: TddCoordinationContext,
    behavior_id: str,
    blocked_phase: str,
    blocked_reason: str | None,
) -> TddCoordinationResult:
    return TddCoordinationResult(
        completed_behavior_ids=context.completed_behavior_ids,
        attempts=context.attempts,
        current_binding=context.current_binding,
        final_revision=context.current_binding.base_sha,
        behaviors=context.behaviors,
        blocked_behavior_id=behavior_id,
        blocked_phase=blocked_phase,
        blocked_reason=blocked_reason,
    )


def _result_from_context(context: TddCoordinationContext) -> TddCoordinationResult:
    return TddCoordinationResult(
        completed_behavior_ids=context.completed_behavior_ids,
        attempts=context.attempts,
        current_binding=context.current_binding,
        final_revision=context.current_binding.base_sha,
        behaviors=context.behaviors,
    )


def _result_from_snapshot(snapshot: TddSnapshot) -> TddCoordinationResult:
    return TddCoordinationResult(
        completed_behavior_ids=list(snapshot.completed_behavior_ids),
        attempts=list(snapshot.attempts),
        current_binding=snapshot.repository_binding,
        final_revision=snapshot.current_trusted_revision,
        behaviors=dict(snapshot.behaviors),
        blocked_behavior_id=snapshot.blocked_behavior_id,
        blocked_phase=snapshot.blocked_phase,
        blocked_reason=snapshot.blocked_reason,
    )


def _save_context(repository: TddStateRepository, context: TddCoordinationContext) -> None:
    repository.save(
        TddSnapshot(
            project_id=context.project_id,
            repository_binding=context.current_binding,
            current_trusted_revision=context.current_binding.base_sha,
            completed_behavior_ids=context.completed_behavior_ids,
            attempts=context.attempts,
            behaviors=context.behaviors,
        )
    )


def _save_result(
    repository: TddStateRepository,
    project_id: str,
    result: TddCoordinationResult,
) -> None:
    repository.save(
        TddSnapshot(
            project_id=project_id,
            repository_binding=result.current_binding,
            current_trusted_revision=result.final_revision,
            completed_behavior_ids=result.completed_behavior_ids,
            attempts=result.attempts,
            behaviors=result.behaviors,
            blocked_behavior_id=result.blocked_behavior_id,
            blocked_phase=result.blocked_phase,
            blocked_reason=result.blocked_reason,
        )
    )
