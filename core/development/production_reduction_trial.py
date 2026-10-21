"""One isolated deletion experiment, with the ordinary acceptance unchanged."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import time

from core.development.deterministic_regression import (
    ACCUMULATED_REGRESSION, REGRESSION_CLEAR, REGRESSION_INFRASTRUCTURE_FAILURE,
    DeterministicRegressionService,
)
from core.development.microcycle_domain import RegressionCommandReport, RegressionState
from core.development.production_reduction_acceptance import (
    FrontierReductionVerifier, ReductionFrontierCheckRequest, verify_reduction_acceptance,
)
from core.development.production_reduction_domain import ProductionReductionRequest
from core.development.production_reduction_git import BoundedReductionGit, ReductionRepository
from core.development.production_reduction_journal import ReductionJournal
from core.development.production_reduction_syntax import ReductionOpportunity


@dataclass(frozen=True)
class ReductionTrialRequest:
    authority: ProductionReductionRequest
    best_revision: str
    opportunity: ReductionOpportunity
    number: int
    deadline: float


@dataclass(frozen=True)
class ReductionTrialResult:
    revision: str | None
    regression: RegressionState
    elapsed_seconds: float


@dataclass(frozen=True)
class ReductionTrialDependencies:
    repository: ReductionRepository
    journal: ReductionJournal
    regression: DeterministicRegressionService
    verifier: FrontierReductionVerifier


class ReductionTrial:
    """Never keeps a trial until every original acceptance command has passed."""

    def __init__(self, dependencies: ReductionTrialDependencies):
        self.dependencies = dependencies

    def run(self, request: ReductionTrialRequest) -> ReductionTrialResult:
        deps = self.dependencies
        source = request.authority
        started = time.monotonic()
        name = f"trial-{request.number:04d}"
        pending = {"transformation_id": request.opportunity.transformation_id,
                   "description": request.opportunity.description,
                   "path": request.opportunity.path, "source_revision": request.best_revision,
                   "decision": "pending", "deadline": request.deadline}
        def record_workspace(workspace: Path) -> None:
            pending["workspace"] = str(workspace)
            deps.journal.record((f"{name}.json", pending))

        with deps.repository.trial((request.best_revision, request.opportunity), record_workspace) as workspace:
            git = BoundedReductionGit(workspace, request.deadline)
            tree = deps.repository.snapshot(workspace)
            patch = git.run(("diff", "--cached", "--binary"))
            (deps.journal.root / f"{name}.patch").write_bytes(patch)
            pending["workspace"] = str(workspace)
            deps.journal.record((f"{name}.json", pending))
            missing = tuple(path for path in source.required_artifacts
                            if not (workspace / path).is_file())
            if missing:
                regression = RegressionState(
                    ACCUMULATED_REGRESSION, source.regression_command,
                    reports=(RegressionCommandReport("required_artifacts", (), None,
                             "failed", "Missing required artifacts: " + ", ".join(missing)),),
                )
                deps.journal.record((f"{name}.json", {
                    **pending, "decision": "discarded", "mechanical": "missing_required_artifact",
                    "regression": regression.to_dict(),
                    "elapsed_seconds": time.monotonic() - started,
                }))
                return ReductionTrialResult(None, regression, time.monotonic() - started)
            frontier, result = verify_reduction_acceptance(
                ReductionFrontierCheckRequest(source, workspace, request.deadline),
                (deps.verifier, deps.regression),
            )
            if git.run(("diff-files", "--name-only")).strip():
                raise ValueError("acceptance mutated a tracked reduction trial file")
            if git.run(("ls-files", "--others", "--exclude-standard")).strip():
                raise ValueError("acceptance created an undeclared reduction trial file")
            if git.run(("write-tree",)).decode().strip() != tree:
                raise ValueError("acceptance changed the reduction index")
            revision = None
            if result.status == REGRESSION_CLEAR:
                revision = deps.repository.retain((workspace, tree))
                deps.repository.validate(revision)
            elapsed = time.monotonic() - started
            regression = result.state(source.regression_command)
            deps.journal.record((f"{name}.json", {
                **pending, "decision": "retained" if revision else "discarded",
                "revision": revision, "tree": tree, "regression": regression.to_dict(),
                "frontier": asdict(frontier),
                "elapsed_seconds": elapsed, "syntax": "adapter-validated",
            }))
            if result.status == REGRESSION_INFRASTRUCTURE_FAILURE and time.monotonic() < request.deadline:
                raise ValueError("reduction infrastructure interrupted; verified candidate preserved")
            return ReductionTrialResult(revision, regression, elapsed)
