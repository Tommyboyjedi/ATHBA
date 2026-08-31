"""Compatibility facade for ATHBA failure progression state and policy."""

from core.development.failure_policy import FailureDecisionPolicy, FailureProgressionPolicy
from core.development.failure_records import (
    DependencyDecision,
    FailureDecision,
    FailureObservation,
    RepairPacket,
    SplitChildStep,
    UnclassifiedAnalysis,
    WorkPacketSplit,
)
from core.development.failure_state import FailureProgressState
from core.development.failure_transitions import FailureRecordRequest, PrerequisiteDeferralRequest, RetryBudget, SplitRecordRequest
from core.development.failure_values import (
    ACTIVE_FAILURE_CLASSIFICATIONS,
    FAILURE_ACTIONS,
    FAILURE_PRIORITY,
    LEGACY_FAILURE_CLASSIFICATIONS,
    DependencyDisposition,
    FailureClassification,
    FailureRouteState,
    PacketKind,
    ProgressionAction,
    RetryRoute,
)

__all__ = [
    "ACTIVE_FAILURE_CLASSIFICATIONS",
    "DependencyDecision",
    "DependencyDisposition",
    "FAILURE_ACTIONS",
    "FAILURE_PRIORITY",
    "LEGACY_FAILURE_CLASSIFICATIONS",
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
    "SplitChildStep",
    "SplitRecordRequest",
    "UnclassifiedAnalysis",
    "WorkPacketSplit",
]
