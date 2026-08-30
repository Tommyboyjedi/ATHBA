from __future__ import annotations

from dataclasses import dataclass

from core.development.failure_records import DependencyDecision, FailureDecision, RepairPacket
from core.development.failure_state import FailureProgressState
from core.development.failure_values import DependencyDisposition, FailureRouteState, RetryRoute


@dataclass(frozen=True)
class RetryBudget:
    state: FailureProgressState
    route: RetryRoute
    budget: int


@dataclass(frozen=True)
class FailureRecordRequest:
    state: FailureProgressState
    decision: FailureDecision
    route: RetryRoute | None = None
    packet: RepairPacket | None = None
    next_state: FailureRouteState | None = None
    blocker: str | None = None


@dataclass(frozen=True)
class PrerequisiteDeferralRequest:
    state: FailureProgressState
    decision: FailureDecision
    requirement_ref: str
    prerequisite_refs: list[str]


class FailureRetryPolicy:
    def retry_allowed(self, request: RetryBudget) -> bool:
        if request.budget < 0:
            raise ValueError("retry budget cannot be negative")
        return request.state.retry_counts.get(request.route.value, 0) < request.budget


class FailureStateTransitions:
    def record(self, request: FailureRecordRequest) -> FailureProgressState:
        retry_counts = self._recorded_retry_counts(request)
        return FailureProgressState(
            state=request.next_state or request.state.state,
            history=[*request.state.history, request.decision],
            retry_counts=retry_counts,
            deferred_requirement_refs=list(request.state.deferred_requirement_refs),
            prerequisite_links={key: list(value) for key, value in request.state.prerequisite_links.items()},
            split_children={key: list(value) for key, value in request.state.split_children.items()},
            repair_packets=[*request.state.repair_packets, *([] if request.packet is None else [request.packet])],
            dependency_decisions=list(request.state.dependency_decisions),
            splits=list(request.state.splits),
            unclassified_analysis=request.state.unclassified_analysis,
            blocker=request.blocker if request.blocker is not None else request.state.blocker,
        )

    def defer_for_prerequisites(self, request: PrerequisiteDeferralRequest) -> FailureProgressState:
        if not request.prerequisite_refs:
            raise ValueError("dependency deferral requires at least one prerequisite")
        recorded = self.record(
            FailureRecordRequest(
                state=request.state,
                decision=request.decision,
                next_state=FailureRouteState.DEFERRED_DEPENDENCY,
            )
        )
        links = {key: list(value) for key, value in recorded.prerequisite_links.items()}
        links[request.requirement_ref] = list(request.prerequisite_refs)
        return FailureProgressState(
            state=FailureRouteState.DEFERRED_DEPENDENCY,
            history=recorded.history,
            retry_counts=recorded.retry_counts,
            deferred_requirement_refs=[*dict.fromkeys([*recorded.deferred_requirement_refs, request.requirement_ref])],
            prerequisite_links=links,
            split_children=recorded.split_children,
            repair_packets=recorded.repair_packets,
            dependency_decisions=[
                *recorded.dependency_decisions,
                DependencyDecision(
                    disposition=DependencyDisposition.ALREADY_PLANNED,
                    parent_requirement_ref=request.requirement_ref,
                    prerequisite_refs=list(request.prerequisite_refs),
                    rationale="Declared Behavior Contract prerequisites are not semantically approved.",
                ),
            ],
            splits=recorded.splits,
            unclassified_analysis=recorded.unclassified_analysis,
            blocker=recorded.blocker,
        )

    def _recorded_retry_counts(self, request: FailureRecordRequest) -> dict[str, int]:
        retry_counts = dict(request.state.retry_counts)
        if request.route is None:
            return retry_counts
        route_key = request.route.value
        retry_counts[route_key] = retry_counts.get(route_key, 0) + 1
        return retry_counts
