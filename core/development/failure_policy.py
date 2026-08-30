from __future__ import annotations

from dataclasses import dataclass, field

from core.development.failure_records import FailureDecision, FailureObservation
from core.development.failure_state import FailureProgressState
from core.development.failure_transitions import (
    FailureRecordRequest,
    FailureRetryPolicy,
    FailureStateTransitions,
    PrerequisiteDeferralRequest,
    RetryBudget,
)
from core.development.failure_values import (
    FAILURE_ACTIONS,
    FAILURE_PRIORITY,
    FailureClassification,
)


class FailureDecisionPolicy:
    def decide(self, observations: list[FailureObservation]) -> FailureDecision:
        if not observations:
            raise ValueError("at least one failure observation is required")
        plausible = sorted({item for observation in observations for item in observation.plausible}, key=FAILURE_PRIORITY.__getitem__)
        dominant = plausible[0] if plausible else FailureClassification.UNCLASSIFIED_FAILURE
        if not plausible:
            plausible = [dominant]
        return FailureDecision(
            observations=list(observations),
            plausible=plausible,
            dominant=dominant,
            priority=FAILURE_PRIORITY[dominant],
            action=FAILURE_ACTIONS[dominant],
        )


@dataclass(frozen=True)
class FailureProgressionPolicy:
    decision_policy: FailureDecisionPolicy = field(default_factory=FailureDecisionPolicy)
    retry_policy: FailureRetryPolicy = field(default_factory=FailureRetryPolicy)
    transitions: FailureStateTransitions = field(default_factory=FailureStateTransitions)

    def decide(self, observations: list[FailureObservation]) -> FailureDecision:
        return self.decision_policy.decide(observations)

    def retry_allowed(self, request: RetryBudget) -> bool:
        return self.retry_policy.retry_allowed(request)

    def record(self, request: FailureRecordRequest) -> FailureProgressState:
        return self.transitions.record(request)

    def defer_for_prerequisites(self, request: PrerequisiteDeferralRequest) -> FailureProgressState:
        return self.transitions.defer_for_prerequisites(request)
