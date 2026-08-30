from __future__ import annotations

from dataclasses import dataclass, replace

from core.development.failure_policy import FailureProgressionPolicy
from core.development.failure_records import DependencyDecision, FailureDecision, FailureObservation, RepairPacket
from core.development.failure_progression import FailureRecordRequest, PrerequisiteDeferralRequest
from core.development.failure_state import TERMINAL_CONTRACT_POOLS
from core.development.failure_values import FailureClassification, FailureRouteState, PacketKind, ProgressionAction, RetryRoute
from core.development.tdd_phase_execution import PhaseOutcome
from core.development.tdd_progression import BehaviorContract, BehaviorContractRunState, ContractCycleRecord, SemanticReviewResult, TddPhase, TddPhaseState
from core.development.tdd_progression_values import ContractPoolStatus, ReviewVerdict
from core.development.tdd_progression_validation import enum_value
from core.development.work_unit import DevelopmentWorkUnit


@dataclass(frozen=True)
class FailureTransition:
    decision: FailureDecision
    route_state: FailureRouteState
    next_pool: str
    cycle_pool: str
    return_now: bool
    retry_route: RetryRoute | None = None
    blocker: str | None = None
    packet: RepairPacket | None = None
    updated_contract: BehaviorContract | None = None
    dependency_decision: DependencyDecision | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "next_pool", enum_value(self.next_pool, ContractPoolStatus, "failure next pool"))
        object.__setattr__(self, "cycle_pool", enum_value(self.cycle_pool, ContractPoolStatus, "failure cycle pool"))
        if self.route_state is FailureRouteState.AWAITING_REPAIR and self.retry_route is None:
            raise ValueError("retry transitions must identify a retry route")
        if self.next_pool in TERMINAL_CONTRACT_POOLS and not self.return_now:
            raise ValueError("terminal failure transitions must return now")


@dataclass(frozen=True)
class CandidateFailureTransitionRequest:
    run_state: BehaviorContractRunState
    phase: TddPhase
    phase_state: TddPhaseState


@dataclass(frozen=True)
class ReviewFailureTransitionRequest:
    run_state: BehaviorContractRunState
    cycle: ContractCycleRecord


def candidate_failure_observation(phase: TddPhase, outcome: PhaseOutcome) -> FailureObservation:
    result = outcome.execution_result
    message = outcome.blocked_reason or outcome.phase_state.error or f"{phase.value} phase failed"
    evidence_refs = [item for item in [outcome.phase_state.evidence_location] if item]
    status = outcome.phase_state.status
    text = " ".join(item for item in [message, outcome.phase_state.error, None if result is None else result.error, status] if item).lower()
    plausible: list[FailureClassification] = []
    if status == "transport_error":
        plausible.append(FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE)
    if any(token in text for token in ("runtime executable", "pytest is unavailable", "environment", "dependency environment")):
        plausible.append(FailureClassification.ENVIRONMENT_FAILURE)
    if any(token in text for token in ("timeout", "out of memory", "no space left", "resource exhausted")):
        plausible.append(FailureClassification.RESOURCE_LIMIT_FAILURE)
    if any(token in text for token in ("syntaxerror", "parse error", "invalid syntax")):
        plausible.append(FailureClassification.SYNTAX_OR_PARSE_FAILURE)
    if any(token in text for token in ("build failed", "linker", "link failure", "packaging failed")):
        plausible.append(FailureClassification.BUILD_OR_LINK_FAILURE)
    if any(token in text for token in ("error collecting", "importerror", "modulenotfounderror", "bootstrap")):
        plausible.append(FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE)
    if any(token in text for token in ("path_policy", "policy", "unauthorized")):
        plausible.append(FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION)
    if any(token in text for token in ("changed_paths", "allowed_paths", "out-of-scope")):
        plausible.append(FailureClassification.CHANGE_SCOPE_VIOLATION)
    if not plausible:
        plausible.append(FailureClassification.TESTER_CANDIDATE_DEFECT if phase is TddPhase.RED else FailureClassification.DEVELOPER_CANDIDATE_DEFECT)
    return FailureObservation(
        source=f"{phase.value}_execution",
        message=message,
        evidence_refs=evidence_refs,
        plausible=plausible,
        candidate_revision=None if result is None else result.accepted_revision,
        status=status,
    )


def review_failure_observation(review: SemanticReviewResult) -> FailureObservation:
    classification = FailureClassification.REVIEW_QUALITY_FAILURE
    if review.verdict == ReviewVerdict.REPLAN_REQUIRED.value:
        classification = FailureClassification.SEMANTIC_INTEGRATION_FAILURE
    return FailureObservation(
        source="senior_review",
        message=review.rationale,
        evidence_refs=list(review.evidence_refs),
        plausible=[classification],
        candidate_revision=review.candidate_revision,
        stdout="\n".join(review.findings) or None,
        status=review.verdict,
    )


def transition_for_candidate_repair(
    decision: FailureDecision,
    phase: TddPhase,
    work_unit: DevelopmentWorkUnit,
    trusted_revision: str | None,
    observation: FailureObservation,
    retry_allowed: bool,
) -> FailureTransition:
    route = _retry_route(decision.action, phase)
    role = "Tester" if route is RetryRoute.TESTER_REPAIR else "Developer"
    packet = RepairPacket(
        kind=PacketKind.REPAIR,
        role=role,
        work_unit_id=work_unit.id,
        trusted_revision=trusted_revision,
        original_objective=work_unit.objective,
        allowed_paths=list(work_unit.allowed_paths),
        classification=decision.dominant,
        previous_candidate=observation.candidate_revision,
        evidence=[observation.message, *observation.evidence_refs],
    )
    if retry_allowed:
        return FailureTransition(
            decision=decision,
            route_state=FailureRouteState.AWAITING_REPAIR,
            next_pool=ContractPoolStatus.CYCLE_ACTIVE.value,
            cycle_pool=ContractPoolStatus.CYCLE_ACTIVE.value,
            return_now=False,
            retry_route=route,
            blocker=f"{decision.dominant.value}: retrying {role} from trusted revision",
            packet=packet,
        )
    return FailureTransition(
        decision=decision,
        route_state=FailureRouteState.ACTIVE,
        next_pool=ContractPoolStatus.REPLAN_READY.value,
        cycle_pool=ContractPoolStatus.REPLAN_READY.value,
        return_now=True,
        blocker=f"{decision.dominant.value}: {observation.message}",
        packet=packet,
    )


def transition_for_dependency_deferral(
    decision: FailureDecision,
    blocker: str,
    updated_contract: BehaviorContract,
    dependency_decision: DependencyDecision,
) -> FailureTransition:
    return FailureTransition(
        decision=decision,
        route_state=FailureRouteState.DEFERRED_DEPENDENCY,
        next_pool=ContractPoolStatus.TDD_READY.value,
        cycle_pool=ContractPoolStatus.REPLAN_READY.value,
        return_now=True,
        blocker=blocker,
        updated_contract=updated_contract,
        dependency_decision=dependency_decision,
    )


def transition_for_environment(decision: FailureDecision, blocker: str, recovered: bool) -> FailureTransition:
    if recovered:
        return FailureTransition(
            decision=decision,
            route_state=FailureRouteState.ACTIVE,
            next_pool=ContractPoolStatus.CYCLE_ACTIVE.value,
            cycle_pool=ContractPoolStatus.CYCLE_ACTIVE.value,
            return_now=False,
            retry_route=RetryRoute.ENVIRONMENT_RECOVERY,
            blocker="environment recovered; rerunning from trusted revision",
        )
    return FailureTransition(
        decision=decision,
        route_state=FailureRouteState.BLOCKED_ENVIRONMENT,
        next_pool=ContractPoolStatus.BLOCKED_ENVIRONMENT.value,
        cycle_pool=ContractPoolStatus.BLOCKED_ENVIRONMENT.value,
        return_now=True,
        blocker=f"{decision.dominant.value}: {blocker}",
    )


def transition_for_executor_block(decision: FailureDecision, blocker: str) -> FailureTransition:
    return _terminal_transition(decision, FailureRouteState.BLOCKED_EXECUTOR, ContractPoolStatus.BLOCKED_EXECUTOR, blocker)


def transition_for_split_required(decision: FailureDecision, blocker: str) -> FailureTransition:
    return _terminal_transition(decision, FailureRouteState.SPLIT_REQUIRED, ContractPoolStatus.SPLIT_REQUIRED, blocker)


def transition_for_replan(decision: FailureDecision, blocker: str) -> FailureTransition:
    return FailureTransition(
        decision=decision,
        route_state=FailureRouteState.ACTIVE,
        next_pool=ContractPoolStatus.REPLAN_READY.value,
        cycle_pool=ContractPoolStatus.REPLAN_READY.value,
        return_now=True,
        blocker=blocker,
    )


def transition_for_block(decision: FailureDecision, route_state: FailureRouteState, next_pool: ContractPoolStatus, blocker: str) -> FailureTransition:
    return _terminal_transition(decision, route_state, next_pool, blocker)


def transition_for_review_repair(decision: FailureDecision, exhausted: bool, blocker: str) -> FailureTransition:
    if exhausted:
        return transition_for_replan(decision, blocker)
    return FailureTransition(
        decision=decision,
        route_state=FailureRouteState.AWAITING_REPAIR,
        next_pool=ContractPoolStatus.REPAIR_READY.value,
        cycle_pool=ContractPoolStatus.REPAIR_READY.value,
        return_now=False,
        retry_route=RetryRoute.REVIEW_REPAIR,
        blocker=None,
    )


def apply_candidate_failure_transition(
    request: CandidateFailureTransitionRequest,
    transition: FailureTransition,
    failure_policy: FailureProgressionPolicy,
) -> BehaviorContractRunState:
    cycle = request.run_state.current_cycle()
    if cycle is None:
        raise ValueError("failed candidate routing requires an active cycle")
    progress = _record_progress(request.run_state, transition, failure_policy)
    phase_state = request.phase_state
    cycle = _cycle_with_phase_state(cycle, request.phase, phase_state, transition.cycle_pool)
    contract = transition.updated_contract or request.run_state.contract
    return replace(
        request.run_state,
        current_pool=transition.next_pool,
        contract=replace(contract, status=transition.next_pool),
        blocked_reason=transition.blocker,
        cycles=_replace_current_cycle(request.run_state.cycles, cycle),
        failure_progress=progress,
    )


def apply_review_failure_transition(
    request: ReviewFailureTransitionRequest,
    transition: FailureTransition,
    failure_policy: FailureProgressionPolicy,
) -> BehaviorContractRunState:
    progress = _record_progress(request.run_state, transition, failure_policy)
    contract = request.run_state.contract
    cycle = replace(request.cycle, pool=transition.cycle_pool)
    return replace(
        request.run_state,
        current_pool=transition.next_pool,
        contract=replace(contract, status=transition.next_pool),
        blocked_reason=transition.blocker,
        cycles=_replace_current_cycle(request.run_state.cycles, cycle),
        failure_progress=progress,
    )


def _record_progress(
    run_state: BehaviorContractRunState,
    transition: FailureTransition,
    failure_policy: FailureProgressionPolicy,
):
    if transition.route_state is FailureRouteState.DEFERRED_DEPENDENCY and transition.dependency_decision is not None:
        progress = failure_policy.defer_for_prerequisites(
            PrerequisiteDeferralRequest(
                state=run_state.failure_progress,
                decision=transition.decision,
                requirement_ref=transition.dependency_decision.parent_requirement_ref,
                prerequisite_refs=transition.dependency_decision.prerequisite_refs,
            )
        )
        return replace(progress, dependency_decisions=[*progress.dependency_decisions[:-1], transition.dependency_decision])
    return failure_policy.record(
        FailureRecordRequest(
            state=run_state.failure_progress,
            decision=transition.decision,
            route=transition.retry_route,
            packet=transition.packet,
            next_state=transition.route_state,
            blocker=transition.blocker,
        )
    )


def _retry_route(action: ProgressionAction, phase: TddPhase) -> RetryRoute:
    if action is ProgressionAction.REPAIR_TESTER:
        return RetryRoute.TESTER_REPAIR
    if action is ProgressionAction.REPAIR_DEVELOPER:
        return RetryRoute.DEVELOPER_REPAIR
    return RetryRoute.TESTER_REPAIR if phase is TddPhase.RED else RetryRoute.DEVELOPER_REPAIR


def _terminal_transition(
    decision: FailureDecision,
    route_state: FailureRouteState,
    next_pool: ContractPoolStatus,
    blocker: str,
) -> FailureTransition:
    return FailureTransition(
        decision=decision,
        route_state=route_state,
        next_pool=next_pool.value,
        cycle_pool=next_pool.value,
        return_now=True,
        blocker=f"{decision.dominant.value}: {blocker}",
    )


def _cycle_with_phase_state(cycle, phase: TddPhase, phase_state, pool: str):
    updates = {"pool": pool}
    if phase is TddPhase.RED:
        updates["red_phase"] = phase_state
    else:
        updates["green_phase"] = phase_state
    return replace(cycle, **updates)


def _replace_current_cycle(cycles, replacement):
    return [*cycles[:-1], replacement]
