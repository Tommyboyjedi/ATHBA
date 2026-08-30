"""Compatibility facade for ATHBA failure progression state and policy."""

from core.development.failure_policy import FailureDecisionPolicy, FailureProgressionPolicy
from core.development.failure_records import (
    DependencyDecision,
    FailureDecision,
    FailureObservation,
    RepairPacket,
    UnclassifiedAnalysis,
    WorkPacketSplit,
)
from core.development.failure_state import FailureProgressState
from core.development.failure_transitions import FailureRecordRequest, PrerequisiteDeferralRequest, RetryBudget
from core.development.failure_values import (
    FAILURE_ACTIONS,
    FAILURE_PRIORITY,
    DependencyDisposition,
    FailureClassification,
    FailureRouteState,
    PacketKind,
    ProgressionAction,
    RetryRoute,
)

__all__ = [
    "DependencyDecision",
    "DependencyDisposition",
    "FAILURE_ACTIONS",
    "FAILURE_PRIORITY",
    "FailureClassification",
    "FailureDecision",
    "FailureDecisionPolicy",
    "FailureObservation",
    "FailureProgressState",
    "FailureProgressionPolicy",
    "FailureRecordRequest",
    "FailureRouteState",
    "PacketKind",
    "PrerequisiteDeferralRequest",
    "ProgressionAction",
    "RepairPacket",
    "RetryBudget",
    "RetryRoute",
    "UnclassifiedAnalysis",
    "WorkPacketSplit",
]
