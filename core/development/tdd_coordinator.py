"""Orchestrate a deterministic RED/GREEN TDD loop through Rack AI."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Iterable, Protocol

from core.datastore.repos.tdd_state_repo import TddStateRepo
from core.development.progression import ExecutionAttemptRecord
from core.development.tdd_progression import (
    TddBehavior,
    TddBehaviorProgress,
    TddPhase,
    TddPhaseState,
    TddSnapshot,
    green_work_unit_id,
    red_work_unit_id,
)
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus
from core.execution.rack_ai_contract import RepositoryBinding
from core.execution.work_unit_gateway import WorkUnitExecutionGateway, WorkUnitExecutionResult

RED_ALREADY_SATISFIED_FRAGMENT = "RED check failed: test unexpectedly passed"


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


class TddCoordinator:
    """Run one predefined RED->GREEN cycle per behavior in order."""

    def __init__(
        self,
        gateway: WorkUnitExecutionGateway,
        repository_binding: RepositoryBinding,
        state_repo: TddStateRepository | None = None,
        tester_factory: TesterWorkUnitFactory | None = None,
        developer_factory: DeveloperWorkUnitFactory | None = None,
    ):
        self.gateway = gateway
        self.repository_binding = repository_binding
        self.state_repo = state_repo or TddStateRepo()
        self.tester_factory = tester_factory or TesterWorkUnitFactory()
        self.developer_factory = developer_factory or DeveloperWorkUnitFactory()

    async def run(self, behaviors: Iterable[TddBehavior]) -> TddCoordinationResult:
        ordered = list(behaviors)
        if not ordered:
            return TddCoordinationResult(
                completed_behavior_ids=[],
                attempts=[],
                current_binding=self.repository_binding,
                final_revision=self.repository_binding.base_sha,
                behaviors={},
            )

        project_id = ordered[0].project_id
        snapshot = self.state_repo.load(project_id)
        if snapshot is not None and snapshot.blocked_behavior_id is not None:
            return self._result_from_snapshot(snapshot)

        current_binding = snapshot.repository_binding if snapshot else self.repository_binding
        attempts = list(snapshot.attempts) if snapshot else []
        completed_behavior_ids = list(snapshot.completed_behavior_ids) if snapshot else []
        progress = dict(snapshot.behaviors) if snapshot else {}

        for behavior in ordered:
            progress.setdefault(behavior.id, TddBehaviorProgress.from_behavior(behavior))

        for behavior in ordered:
            if behavior.id in completed_behavior_ids:
                continue

            behavior_progress = progress[behavior.id]
            if behavior_progress.status == "completed":
                completed_behavior_ids.append(behavior.id)
                continue

            if behavior_progress.red_phase.accepted_revision is None:
                red_outcome = await self._execute_phase(
                    phase=TddPhase.RED,
                    work_unit=self.tester_factory.build(behavior),
                    base_binding=current_binding,
                )
                attempts.append(red_outcome.attempt)
                progress[behavior.id] = replace(
                    behavior_progress,
                    current_phase=TddPhase.GREEN.value if red_outcome.accepted else TddPhase.RED.value,
                    status="red_accepted" if red_outcome.accepted else "blocked",
                    red_phase=red_outcome.phase_state,
                )
                behavior_progress = progress[behavior.id]
                if not red_outcome.accepted:
                    return self._block_and_save(
                        project_id,
                        current_binding,
                        attempts,
                        completed_behavior_ids,
                        progress,
                        behavior.id,
                        TddPhase.RED.value,
                        red_outcome.blocked_reason,
                    )

                current_binding = current_binding.with_base_sha(red_outcome.phase_state.accepted_revision)
                self._save_snapshot(project_id, current_binding, attempts, completed_behavior_ids, progress)
            else:
                current_binding = current_binding.with_base_sha(behavior_progress.red_phase.accepted_revision)

            if behavior_progress.green_phase.accepted_revision is None:
                green_outcome = await self._execute_phase(
                    phase=TddPhase.GREEN,
                    work_unit=self.developer_factory.build(behavior),
                    base_binding=current_binding,
                )
                attempts.append(green_outcome.attempt)
                progress[behavior.id] = replace(
                    behavior_progress,
                    current_phase=TddPhase.COMPLETE.value if green_outcome.accepted else TddPhase.GREEN.value,
                    status="completed" if green_outcome.accepted else "blocked",
                    green_phase=green_outcome.phase_state,
                )
                behavior_progress = progress[behavior.id]
                if not green_outcome.accepted:
                    return self._block_and_save(
                        project_id,
                        current_binding,
                        attempts,
                        completed_behavior_ids,
                        progress,
                        behavior.id,
                        TddPhase.GREEN.value,
                        green_outcome.blocked_reason,
                    )

                current_binding = current_binding.with_base_sha(green_outcome.phase_state.accepted_revision)
                if behavior.id not in completed_behavior_ids:
                    completed_behavior_ids.append(behavior.id)
                self._save_snapshot(project_id, current_binding, attempts, completed_behavior_ids, progress)
            else:
                current_binding = current_binding.with_base_sha(behavior_progress.green_phase.accepted_revision)
                if behavior.id not in completed_behavior_ids:
                    completed_behavior_ids.append(behavior.id)

        result = TddCoordinationResult(
            completed_behavior_ids=completed_behavior_ids,
            attempts=attempts,
            current_binding=current_binding,
            final_revision=current_binding.base_sha,
            behaviors=progress,
        )
        self._save_result(project_id, result)
        return result

    async def _execute_phase(
        self,
        *,
        phase: TddPhase,
        work_unit: DevelopmentWorkUnit,
        base_binding: RepositoryBinding,
    ) -> "_PhaseOutcome":
        recorded_at = _utc_now()
        base_sha = base_binding.base_sha
        try:
            result = await self.gateway.execute(work_unit, base_binding)
        except Exception as error:
            attempt = ExecutionAttemptRecord.transport_failure(
                work_unit.id,
                base_sha=base_sha,
                recorded_at=recorded_at,
                error=str(error),
            )
            return _PhaseOutcome(
                attempt=attempt,
                phase_state=TddPhaseState(
                    phase=phase.value,
                    work_unit_id=work_unit.id,
                    base_sha=base_sha,
                    status="transport_error",
                    error=str(error),
                    recorded_at=recorded_at,
                ),
                accepted=False,
                blocked_reason=f"{phase.value} phase transport failure",
            )

        attempt = ExecutionAttemptRecord.from_result(result, base_sha=base_sha, recorded_at=recorded_at)
        phase_state = _phase_state_from_result(phase, work_unit.id, base_sha, recorded_at, result)
        if not result.accepted:
            return _PhaseOutcome(
                attempt=attempt,
                phase_state=phase_state,
                accepted=False,
                blocked_reason=_blocked_reason_for_result(phase, result),
                execution_result=result,
            )
        if not result.accepted_revision:
            return _PhaseOutcome(
                attempt=attempt,
                phase_state=phase_state,
                accepted=False,
                blocked_reason=f"accepted {phase.value} phase missing trusted accepted revision",
                execution_result=result,
            )
        return _PhaseOutcome(attempt=attempt, phase_state=phase_state, accepted=True, execution_result=result)

    def _block_and_save(
        self,
        project_id: str,
        current_binding: RepositoryBinding,
        attempts: list[ExecutionAttemptRecord],
        completed_behavior_ids: list[str],
        behaviors: dict[str, TddBehaviorProgress],
        blocked_behavior_id: str,
        blocked_phase: str,
        blocked_reason: str | None,
    ) -> TddCoordinationResult:
        result = TddCoordinationResult(
            completed_behavior_ids=completed_behavior_ids,
            attempts=attempts,
            current_binding=current_binding,
            final_revision=current_binding.base_sha,
            behaviors=behaviors,
            blocked_behavior_id=blocked_behavior_id,
            blocked_phase=blocked_phase,
            blocked_reason=blocked_reason,
        )
        self._save_result(project_id, result)
        return result

    def _save_snapshot(
        self,
        project_id: str,
        current_binding: RepositoryBinding,
        attempts: list[ExecutionAttemptRecord],
        completed_behavior_ids: list[str],
        behaviors: dict[str, TddBehaviorProgress],
    ) -> None:
        self.state_repo.save(
            TddSnapshot(
                project_id=project_id,
                repository_binding=current_binding,
                current_trusted_revision=current_binding.base_sha,
                completed_behavior_ids=completed_behavior_ids,
                attempts=attempts,
                behaviors=behaviors,
            )
        )

    def _save_result(self, project_id: str, result: TddCoordinationResult) -> None:
        self.state_repo.save(
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

    def _result_from_snapshot(self, snapshot: TddSnapshot) -> TddCoordinationResult:
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


@dataclass(frozen=True)
class _PhaseOutcome:
    attempt: ExecutionAttemptRecord
    phase_state: TddPhaseState
    accepted: bool
    blocked_reason: str | None = None
    execution_result: WorkUnitExecutionResult | None = None


def _phase_state_from_result(
    phase: TddPhase,
    work_unit_id: str,
    base_sha: str | None,
    recorded_at: str,
    result: WorkUnitExecutionResult,
) -> TddPhaseState:
    return TddPhaseState(
        phase=phase.value,
        work_unit_id=work_unit_id,
        base_sha=base_sha,
        status=_phase_status_for_result(phase, result),
        accepted_revision=result.accepted_revision,
        evidence_location=result.evidence_location,
        change_id=result.change_id,
        branch=result.branch,
        worktree_path=result.worktree_path,
        selected_worker_id=result.selected_worker_id,
        error=result.error,
        recorded_at=recorded_at,
    )


def _phase_status_for_result(phase: TddPhase, result: WorkUnitExecutionResult) -> str:
    if phase == TddPhase.RED and _is_red_already_satisfied(result):
        return "already_satisfied"
    return result.status


def _blocked_reason_for_result(phase: TddPhase, result: WorkUnitExecutionResult) -> str:
    if phase == TddPhase.RED and _is_red_already_satisfied(result):
        return "red phase found behavior already satisfied before RED"
    return f"{phase.value} phase returned structured non-accepted result: {result.status}"


def _is_red_already_satisfied(result: WorkUnitExecutionResult) -> bool:
    if result.accepted:
        return False
    if result.status != "checks_failed":
        return False
    return RED_ALREADY_SATISFIED_FRAGMENT in (result.error or "")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
