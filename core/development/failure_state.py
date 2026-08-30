from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from core.development.failure_records import (
    DependencyDecision,
    FailureDecision,
    RepairPacket,
    UnclassifiedAnalysis,
    WorkPacketSplit,
)
from core.development.failure_values import FailureRouteState
from core.development.tdd_progression_values import ContractPoolStatus

TERMINAL_CONTRACT_POOLS = {
    ContractPoolStatus.REPLAN_READY.value,
    ContractPoolStatus.COMPLETED.value,
    ContractPoolStatus.BLOCKED_EXECUTOR.value,
    ContractPoolStatus.BLOCKED_ENVIRONMENT.value,
    ContractPoolStatus.BLOCKED_ARCHITECTURE.value,
    ContractPoolStatus.BLOCKED_AMBIGUITY.value,
    ContractPoolStatus.BLOCKED_UNCLASSIFIED.value,
    ContractPoolStatus.SPLIT_REQUIRED.value,
}
BLOCKED_CONTRACT_POOLS = {
    ContractPoolStatus.BLOCKED_EXECUTOR.value,
    ContractPoolStatus.BLOCKED_ENVIRONMENT.value,
    ContractPoolStatus.BLOCKED_ARCHITECTURE.value,
    ContractPoolStatus.BLOCKED_AMBIGUITY.value,
    ContractPoolStatus.BLOCKED_UNCLASSIFIED.value,
    ContractPoolStatus.SPLIT_REQUIRED.value,
}
BLOCKED_ROUTE_STATES = {
    FailureRouteState.BLOCKED_EXECUTOR.value,
    FailureRouteState.BLOCKED_ENVIRONMENT.value,
    FailureRouteState.BLOCKED_ARCHITECTURE.value,
    FailureRouteState.BLOCKED_AMBIGUITY.value,
    FailureRouteState.BLOCKED_UNCLASSIFIED.value,
    FailureRouteState.SPLIT_REQUIRED.value,
}


@dataclass(frozen=True)
class FailureProgressState:
    """Durable policy state attached to a behavior-contract run."""

    state: FailureRouteState = FailureRouteState.ACTIVE
    history: list[FailureDecision] = field(default_factory=list)
    retry_counts: dict[str, int] = field(default_factory=dict)
    deferred_requirement_refs: list[str] = field(default_factory=list)
    prerequisite_links: dict[str, list[str]] = field(default_factory=dict)
    split_children: dict[str, list[str]] = field(default_factory=dict)
    repair_packets: list[RepairPacket] = field(default_factory=list)
    dependency_decisions: list[DependencyDecision] = field(default_factory=list)
    splits: list[WorkPacketSplit] = field(default_factory=list)
    unclassified_analysis: UnclassifiedAnalysis | None = None
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "history": [item.to_dict() for item in self.history],
            "retry_counts": dict(self.retry_counts),
            "deferred_requirement_refs": list(self.deferred_requirement_refs),
            "prerequisite_links": {key: list(value) for key, value in self.prerequisite_links.items()},
            "split_children": {key: list(value) for key, value in self.split_children.items()},
            "repair_packets": [item.to_dict() for item in self.repair_packets],
            "dependency_decisions": [item.to_dict() for item in self.dependency_decisions],
            "splits": [item.to_dict() for item in self.splits],
            "unclassified_analysis": None if self.unclassified_analysis is None else self.unclassified_analysis.to_dict(),
            "blocker": self.blocker,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FailureProgressState":
        return cls(
            state=FailureRouteState(str(payload.get("state", FailureRouteState.ACTIVE.value))),
            history=[FailureDecision.from_dict(dict(item)) for item in payload.get("history", [])],
            retry_counts={str(key): int(value) for key, value in dict(payload.get("retry_counts", {})).items()},
            deferred_requirement_refs=[str(item) for item in payload.get("deferred_requirement_refs", [])],
            prerequisite_links={str(key): [str(item) for item in value] for key, value in dict(payload.get("prerequisite_links", {})).items()},
            split_children={str(key): [str(item) for item in value] for key, value in dict(payload.get("split_children", {})).items()},
            repair_packets=[RepairPacket.from_dict(dict(item)) for item in payload.get("repair_packets", [])],
            dependency_decisions=[DependencyDecision.from_dict(dict(item)) for item in payload.get("dependency_decisions", [])],
            splits=[WorkPacketSplit.from_dict(dict(item)) for item in payload.get("splits", [])],
            unclassified_analysis=None if payload.get("unclassified_analysis") is None else UnclassifiedAnalysis.from_dict(dict(payload["unclassified_analysis"])),
            blocker=payload.get("blocker"),
        )




def active_failure_progress_state(failure_progress: FailureProgressState) -> FailureProgressState:
    return replace(failure_progress, state=FailureRouteState.ACTIVE, blocker=None)

def validate_failure_progress_state(
    current_pool: str,
    failure_progress: FailureProgressState,
    blocked_reason: str | None,
) -> None:
    route_state = failure_progress.state.value
    if current_pool == ContractPoolStatus.COMPLETED.value and route_state == FailureRouteState.AWAITING_REPAIR.value:
        raise ValueError("completed runs must not remain in awaiting_repair")
    if current_pool in BLOCKED_CONTRACT_POOLS and not blocked_reason:
        raise ValueError("blocked contract pools require a blocked reason")
    if current_pool == ContractPoolStatus.BLOCKED_EXECUTOR.value and route_state != FailureRouteState.BLOCKED_EXECUTOR.value:
        raise ValueError("blocked_executor pool requires blocked_executor failure state")
    if current_pool == ContractPoolStatus.BLOCKED_ENVIRONMENT.value and route_state != FailureRouteState.BLOCKED_ENVIRONMENT.value:
        raise ValueError("blocked_environment pool requires blocked_environment failure state")
    if current_pool == ContractPoolStatus.SPLIT_REQUIRED.value and route_state != FailureRouteState.SPLIT_REQUIRED.value:
        raise ValueError("split_required pool requires split_required failure state")
