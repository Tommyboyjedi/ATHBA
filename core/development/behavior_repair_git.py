"""Typed adapter that lets behavior repair reuse strict frontier Git materialisation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from core.development.behavior_repair import (
    BehaviorRepairCandidate,
    BehaviorRepairCandidateRepository,
    BehaviorRepairCandidateRequest,
)
from core.development.strict_microcycle import (
    FrontierCandidate,
    FrontierCandidateRequest,
    GitFrontierMaterialiser,
)


@dataclass(frozen=True)
class BehaviorRepairGitCandidateRepository:
    materialiser: GitFrontierMaterialiser

    def materialise(self, request: BehaviorRepairCandidateRequest) -> BehaviorRepairCandidate:
        return self.materialiser.materialise(
            FrontierCandidateRequest(request.artifact, request.repository_root, request.test_path)
        )

    def cleanup(self, candidate: BehaviorRepairCandidate) -> None:
        self.materialiser.cleanup(cast(FrontierCandidate, candidate))
