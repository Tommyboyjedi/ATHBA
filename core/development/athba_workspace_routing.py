"""ATHBA-internal classification of model-driven workspace work."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

class AthbaModelWorkKind(str, Enum):
    BEHAVIOR_PLANNING = "behavior_planning"
    GATEKEEPER_ATOMIZATION = "gatekeeper_atomization"
    COMPLETE_SCENARIO_AUTHORING = "complete_scenario_authoring"
    SCENARIO_REPAIR = "scenario_repair"
    SCENARIO_INTENT_REVIEW = "scenario_intent_review"
    FRONTIER_IMPLEMENTATION = "frontier_implementation"
    MECHANICAL_FRONTIER_REPAIR = "mechanical_frontier_repair"
    STRONGER_FRONTIER_FALLBACK = "stronger_frontier_fallback"
    REGRESSION_REPAIR = "regression_repair"
    SENIOR_BEHAVIOR_REVIEW = "senior_behavior_review"
    SEMANTIC_BEHAVIOR_REPAIR = "semantic_behavior_repair"
    FINAL_GATEKEEPER_RECONCILIATION = "final_gatekeeper_reconciliation"

class GenericModelCapability(str, Enum):
    REASONING = "reasoning"
    CODING = "coding"
    VISUAL = "visual"
    AUDIO = "audio"

class WorkspaceComplexity(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"

class AthbaOutboundPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"

@dataclass(frozen=True)
class AthbaExecutionProfile:
    required_capabilities: frozenset[GenericModelCapability]
    complexity: WorkspaceComplexity
    requires_large_context: bool
    priority: AthbaOutboundPriority
    timeout_seconds: int

    def __post_init__(self) -> None:
        if not self.required_capabilities:
            raise ValueError("workspace execution requires at least one capability")
        if type(self.timeout_seconds) is not int or self.timeout_seconds <= 0:
            raise ValueError("workspace timeout must be a positive integer")

@dataclass(frozen=True)
class AthbaWorkspaceIdentity:
    """Opaque identities retained by ATHBA across backend delivery retries."""
    work_id: str
    submission_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in self.values()):
            raise ValueError("workspace identities must be non-empty")

    def values(self) -> tuple[str, str, str]:
        return self.work_id, self.submission_id, self.idempotency_key

@dataclass(frozen=True)
class AthbaProfileResolutionRequest:
    work_kind: AthbaModelWorkKind
    timeout_seconds: int
    requires_large_context: bool = False

class AthbaExecutionProfileResolver:
    """Maps ATHBA-only work names to backend-neutral execution requirements."""
    def resolve(self, request: AthbaProfileResolutionRequest) -> AthbaExecutionProfile | None:
        if request.work_kind in _REASONING_ONLY_KINDS or request.work_kind in _DETERMINISTIC_KINDS:
            return None
        return self._profile_for(request)

    @staticmethod
    def _profile_for(request: AthbaProfileResolutionRequest) -> AthbaExecutionProfile:
        if request.work_kind in _SCENARIO_KINDS:
            return _profile(_REASONING_AND_CODING, WorkspaceComplexity.MEDIUM, False, AthbaOutboundPriority.MEDIUM, request.timeout_seconds)
        if request.work_kind == AthbaModelWorkKind.FRONTIER_IMPLEMENTATION:
            return _profile(_CODING_ONLY, WorkspaceComplexity.SMALL, False, AthbaOutboundPriority.LOW, request.timeout_seconds)
        if request.work_kind == AthbaModelWorkKind.MECHANICAL_FRONTIER_REPAIR:
            return _profile(_CODING_ONLY, WorkspaceComplexity.SMALL, False, AthbaOutboundPriority.MEDIUM, request.timeout_seconds)
        if request.work_kind == AthbaModelWorkKind.STRONGER_FRONTIER_FALLBACK:
            return _profile(_REASONING_AND_CODING, WorkspaceComplexity.MEDIUM, request.requires_large_context, AthbaOutboundPriority.MEDIUM, request.timeout_seconds)
        if request.work_kind == AthbaModelWorkKind.REGRESSION_REPAIR:
            return _profile(_CODING_ONLY, WorkspaceComplexity.MEDIUM, request.requires_large_context, AthbaOutboundPriority.MEDIUM, request.timeout_seconds)
        if request.work_kind == AthbaModelWorkKind.SEMANTIC_BEHAVIOR_REPAIR:
            complexity = WorkspaceComplexity.LARGE if request.requires_large_context else WorkspaceComplexity.MEDIUM
            return _profile(_REASONING_AND_CODING, complexity, request.requires_large_context, AthbaOutboundPriority.MEDIUM, request.timeout_seconds)
        raise ValueError(f"unsupported ATHBA workspace work kind: {request.work_kind.value}")

def _profile(capabilities: frozenset[GenericModelCapability], complexity: WorkspaceComplexity, requires_large_context: bool, priority: AthbaOutboundPriority, timeout_seconds: int) -> AthbaExecutionProfile:
    return AthbaExecutionProfile(capabilities, complexity, requires_large_context, priority, timeout_seconds)

_CODING_ONLY = frozenset({GenericModelCapability.CODING})
_REASONING_AND_CODING = frozenset({GenericModelCapability.REASONING, GenericModelCapability.CODING})
_SCENARIO_KINDS = frozenset({AthbaModelWorkKind.COMPLETE_SCENARIO_AUTHORING, AthbaModelWorkKind.SCENARIO_REPAIR})
_REASONING_ONLY_KINDS = frozenset({AthbaModelWorkKind.BEHAVIOR_PLANNING, AthbaModelWorkKind.GATEKEEPER_ATOMIZATION, AthbaModelWorkKind.SCENARIO_INTENT_REVIEW, AthbaModelWorkKind.SENIOR_BEHAVIOR_REVIEW, AthbaModelWorkKind.FINAL_GATEKEEPER_RECONCILIATION})
_DETERMINISTIC_KINDS: frozenset[AthbaModelWorkKind] = frozenset()
