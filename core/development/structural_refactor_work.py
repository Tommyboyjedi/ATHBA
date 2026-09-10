"""Build one narrow, production-only structural work unit."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from core.development.athba_workspace_routing import AthbaModelWorkKind, AthbaWorkspaceIdentity
from core.development.structural_refactor_domain import StructuralProblem, StructuralRefactorPolicy
from core.development.work_unit import AcceptanceContract, DevelopmentWorkUnit, WorkUnitStatus

STRUCTURAL_INSTRUCTION = (
    "You are the Structural Refactorer. Refactor the existing production code only enough "
    "to resolve the structural incompatibility described below. Preserve all previously "
    "accepted behaviour. Do not implement unrelated behaviour, redesign the application, "
    "edit tests, or perform general cleanup."
)


@dataclass(frozen=True)
class StructuralWorkInput:
    project_id: str
    scenario_id: str
    frontier_index: int
    attempt_number: int
    trusted_revision: str
    problem: StructuralProblem
    production_source: str
    acceptance_commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class StructuralWorkFactory:
    policy: StructuralRefactorPolicy = StructuralRefactorPolicy()

    def build(self, request: StructuralWorkInput) -> DevelopmentWorkUnit:
        logical = f"{request.scenario_id}:{request.frontier_index}:{request.trusted_revision}"
        work_id = hashlib.sha256(logical.encode()).hexdigest()
        identity = hashlib.sha256(f"{logical}:{request.attempt_number}".encode()).hexdigest()
        focused = request.production_source
        objective = STRUCTURAL_INSTRUCTION + "\n" + json.dumps({
            "production": [{"path": request.problem.production_path, "source": focused}],
            "structural_problem": request.problem.description,
        })
        return DevelopmentWorkUnit(
            id=identity, project_id=request.project_id, parent_ticket_id=request.scenario_id,
            objective=objective, allowed_paths=[request.problem.production_path],
            acceptance=AcceptanceContract(
                [list(command) for command in request.acceptance_commands],
                required_artifacts=[request.problem.production_path],
            ),
            max_implementation_attempts=1, timeout_seconds=self.policy.timeout_seconds,
            model_work_kind=AthbaModelWorkKind.STRUCTURAL_REFACTOR,
            workspace_identity=AthbaWorkspaceIdentity(work_id, identity, identity),
            change_key=identity, status=WorkUnitStatus.READY,
        )
