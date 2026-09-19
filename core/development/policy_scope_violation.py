from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.development.failure_records import FailureObservation
from core.development.failure_values import FailureClassification
from core.development.tdd_progression import BehaviorContract, TddPhase, TddStepProposal
from core.development.work_unit import DevelopmentWorkUnit


class PolicyScopeDisposition(Enum):
    ROLE_CANDIDATE_DEFECT = "role_candidate_defect"
    ATHBA_REQUEST_DEFECT = "athba_request_defect"
    PLAN_SCOPE_CHANGE = "plan_scope_change"


@dataclass(frozen=True)
class PolicyScopeResolutionRequest:
    classification: FailureClassification
    contract: BehaviorContract
    phase: TddPhase
    step: TddStepProposal
    work_unit: DevelopmentWorkUnit
    observation: FailureObservation


@dataclass(frozen=True)
class PolicyScopeResolution:
    disposition: PolicyScopeDisposition
    blocker: str | None = None


class PolicyScopeViolationResolver:
    def resolve(self, request: PolicyScopeResolutionRequest) -> PolicyScopeResolution:
        if request.classification not in {
            FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION,
            FailureClassification.CHANGE_SCOPE_VIOLATION,
        }:
            return PolicyScopeResolution(PolicyScopeDisposition.ROLE_CANDIDATE_DEFECT)
        if _has_request_defect(request):
            return PolicyScopeResolution(
                PolicyScopeDisposition.ATHBA_REQUEST_DEFECT,
                _request_defect_message(request),
            )
        if request.classification is FailureClassification.CHANGE_SCOPE_VIOLATION and _is_plan_scope_change(request):
            return PolicyScopeResolution(
                PolicyScopeDisposition.PLAN_SCOPE_CHANGE,
                _plan_scope_message(request),
            )
        return PolicyScopeResolution(PolicyScopeDisposition.ROLE_CANDIDATE_DEFECT)


def _authoritative_allowed_paths(request: PolicyScopeResolutionRequest) -> list[str]:
    return [request.step.test_path] if request.phase is TddPhase.RED else [request.step.production_path]


def _phase_scope_paths(request: PolicyScopeResolutionRequest) -> list[str]:
    return list(request.contract.test_paths) if request.phase is TddPhase.RED else list(request.contract.production_paths)


def _is_plan_scope_change(request: PolicyScopeResolutionRequest) -> bool:
    changed_paths = set(request.observation.changed_paths)
    if not changed_paths:
        return False
    return changed_paths.issubset(set(_phase_scope_paths(request))) and not changed_paths.issubset(set(request.work_unit.allowed_paths))


def _has_request_defect(request: PolicyScopeResolutionRequest) -> bool:
    authoritative = set(_authoritative_allowed_paths(request))
    requested = set(request.work_unit.allowed_paths)
    reported = set(request.observation.allowed_paths or request.work_unit.allowed_paths)
    return requested != authoritative or reported != requested


def _request_defect_message(request: PolicyScopeResolutionRequest) -> str:
    return (
        f"athba_request_defect: {request.phase.value} candidate ran with allowed paths "
        f"{request.observation.allowed_paths or request.work_unit.allowed_paths} "
        f"but authoritative phase paths are {_authoritative_allowed_paths(request)}"
    )


def _plan_scope_message(request: PolicyScopeResolutionRequest) -> str:
    return (
        f"plan_scope_change: {request.phase.value} candidate changed {request.observation.changed_paths} "
        f"while current allowed paths are {request.work_unit.allowed_paths}; "
        f"phase scope remains {_phase_scope_paths(request)}"
    )
