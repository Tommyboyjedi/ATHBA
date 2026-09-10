"""Typed collaborators and repository checks for structural recovery."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from core.development.microcycle_domain import (
    BoundaryAssessment, FrontierMaterialisationRequest, LanguageTestAdapter,
    MicrocycleState, ScenarioFrontier,
)
from core.development.strict_microcycle import (
    FrontierCandidate, FrontierCandidateRequest, StrictMicrocycleRequest, _git,
)
from core.development.structural_refactor_domain import StructuralProblem, StructuralCandidateCheck

if TYPE_CHECKING:
    from core.development.strict_microcycle import StrictMicrocycleService


@dataclass(frozen=True)
class StructuralContext:
    service: StrictMicrocycleService
    request: StrictMicrocycleRequest
    state: MicrocycleState
    adapter: LanguageTestAdapter

    def problem(self) -> StructuralProblem:
        for observation in self.state.boundary_evidence:
            if observation.active_fragment_id == self.state.frontier.active_fragment_id and observation.structural_problem:
                problem = observation.structural_problem
                if problem.production_path != self.request.production_path:
                    raise ValueError("structural problem does not identify authorized production")
                return problem
        raise ValueError("structural recovery requires original boundary evidence")

    def source(self, revision: str) -> str:
        return _git(self.request.repository_root, "show", f"{revision}:{self.problem().production_path}")

    def materialise(self, revision: str, previous: bool = False) -> FrontierCandidate:
        state = self.state
        frontier = state.frontier
        if previous:
            index = frontier.index - 1
            if index < 0:
                raise ValueError("structural recovery requires an accepted prefix")
            ids = tuple(item.fragment_id for item in state.fragments[:index + 1])
            frontier = ScenarioFrontier(state.model.scenario_id, index, ids[-1], ids)
        artifact = self.adapter.materialise_frontier(FrontierMaterialisationRequest(
            state.model, state.fragments, frontier, revision,
        ))
        return self.service.candidates.materialise(FrontierCandidateRequest(
            artifact, self.request.repository_root, state.model.test_path,
        ))

    def candidate_in_scope(self, revision: str) -> bool:
        attempt = self.state.structural_attempts[-1]
        changed = _git(self.request.repository_root, "diff", "--name-only",
                       attempt.trusted_revision, revision).splitlines()
        if changed != [self.problem().production_path]:
            return False
        # Exact Git tree comparison protects tests even if an executor lies.
        _git(self.request.repository_root, "merge-base", "--is-ancestor", attempt.trusted_revision, revision)
        mode = _git(self.request.repository_root, "ls-tree", revision, "--", self.problem().production_path)
        if not mode.startswith("100644 blob "):
            return False
        return self.adapter.validate_structural_candidate(StructuralCandidateCheck(
            self.problem(), self.source(attempt.trusted_revision), self.source(revision),
        ))


def replace_attempt(state: MicrocycleState, **changes) -> MicrocycleState:
    attempt = replace(state.structural_attempts[-1], **changes)
    return replace(state, structural_attempts=(*state.structural_attempts[:-1], attempt))


def evidence(observation: BoundaryAssessment) -> str:
    import json
    return json.dumps(observation.to_dict(), sort_keys=True)
