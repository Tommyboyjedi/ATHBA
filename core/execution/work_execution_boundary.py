"""Classify generic execution boundaries without software-development semantics."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath

from core.development.work_unit import DevelopmentWorkUnit
from core.execution.work_unit_gateway import WorkUnitExecutionResult


class ExecutionBoundaryKind(str, Enum):
    INFRASTRUCTURE = "infrastructure"
    PROTOCOL = "protocol"
    AUTHORITY = "mechanical_authority"


@dataclass
class ExecutionBoundaryFailure(Exception):
    kind: ExecutionBoundaryKind
    detail: str
    evidence_ref: str | None = None


@dataclass(frozen=True)
class ExecutionBoundaryRequest:
    unit: DevelopmentWorkUnit
    result: WorkUnitExecutionResult


def assert_execution_boundary(request: ExecutionBoundaryRequest) -> None:
    unit, result = request.unit, request.result
    if result.work_unit_id != unit.id:
        raise ExecutionBoundaryFailure(ExecutionBoundaryKind.AUTHORITY, "work identity mismatch", result.evidence_location)
    if result.policy_evidence is not None:
        allowed = tuple(PurePosixPath(path) for path in unit.allowed_paths)
        for name in result.policy_evidence.changed_paths:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or not any(path == base or base in path.parents for base in allowed):
                raise ExecutionBoundaryFailure(ExecutionBoundaryKind.AUTHORITY,
                    "candidate changed an immutable or unauthorized path", result.evidence_location)
    external = {
        "backend_unavailable": ExecutionBoundaryKind.INFRASTRUCTURE,
        "capability_unavailable": ExecutionBoundaryKind.INFRASTRUCTURE,
        "temporarily_unavailable": ExecutionBoundaryKind.INFRASTRUCTURE,
        "cancelled": ExecutionBoundaryKind.INFRASTRUCTURE,
        "duplicate_submission": ExecutionBoundaryKind.AUTHORITY,
        "selection_execution_mismatch": ExecutionBoundaryKind.AUTHORITY,
        "malformed_result": ExecutionBoundaryKind.PROTOCOL,
    }
    if result.status in external:
        raise ExecutionBoundaryFailure(external[result.status], result.error or result.status, result.evidence_location)
