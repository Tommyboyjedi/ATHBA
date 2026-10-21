"""Bounded greedy reduction of a verified frontier change; never a minimality proof."""
from __future__ import annotations

from dataclasses import dataclass, replace
import time
import hashlib
from pathlib import Path

from core.development.deterministic_regression import REGRESSION_CLEAR, DeterministicRegressionService
from core.development.production_reduction_domain import (
    ProductionReductionRequest, ProductionReductionResult, ReductionCheckpoint,
    ReductionDeadlineReached, ReductionPolicy,
)
from core.development.production_reduction_git import ReductionRepository, opportunity_digest
from core.development.production_reduction_journal import ReductionJournal
from core.development.production_reduction_syntax import ProductionReductionAdapter, ReductionOpportunity
from core.development.production_reduction_trial import (
    ReductionTrial, ReductionTrialDependencies, ReductionTrialRequest,
)


@dataclass(frozen=True)
class ProductionReductionDependencies:
    evidence_root: Path
    adapter: ProductionReductionAdapter
    regression: DeterministicRegressionService
    policy: ReductionPolicy = ReductionPolicy()


MINIMUM_TRIAL_WINDOW = 5.0
RECOVERY_SAFETY_LIMIT = 20.0


class ProductionChangeReducer:
    """Retains only tested descendants, journaling before optional experiments."""

    def __init__(self, dependencies: ProductionReductionDependencies):
        self.dependencies = dependencies

    def reduce(self, request: ProductionReductionRequest) -> ProductionReductionResult:
        deps = self.dependencies
        if request.initial_regression.status != REGRESSION_CLEAR:
            raise ValueError("only an independently verified GREEN candidate can be reduced")
        if request.initial_regression.command != request.regression_command:
            raise ValueError("reduction cannot change acceptance commands")
        journal = ReductionJournal(deps.evidence_root, request)
        with journal.locked(), journal.measured(deps.policy):
            checkpoint = journal.load(deps.policy)
            if checkpoint is None:
                checkpoint = ReductionCheckpoint(
                    journal.identity, request.candidate_revision, request.initial_regression,
                    time.time() + deps.policy.max_seconds,
                )
                journal.save((checkpoint, deps.policy))
            remaining = max(0.0, min(deps.policy.max_seconds, checkpoint.deadline_unix - time.time()))
            # Recovery never launches a new experiment after its persisted deadline.
            # Exact authority and interrupted-workspace cleanup remain mandatory.
            safety_only = checkpoint.termination is not None or remaining <= MINIMUM_TRIAL_WINDOW
            allowance = RECOVERY_SAFETY_LIMIT if safety_only else remaining
            repository = ReductionRepository(request, time.monotonic() + allowance)
            repository.validate(checkpoint.best_revision)
            repository.recover_trials(journal.root)
            if checkpoint.termination is not None:
                return ProductionReductionResult(checkpoint.best_revision, checkpoint.regression,
                                                 str(journal.root / "checkpoint.json"))
            if remaining <= MINIMUM_TRIAL_WINDOW:
                checkpoint = replace(checkpoint, termination="deadline_reached")
            else:
                trial = ReductionTrial(ReductionTrialDependencies(repository, journal, deps.regression))
                checkpoint = self._search((request, checkpoint), (journal, repository, trial))
            journal.save((checkpoint, deps.policy))
            return ProductionReductionResult(checkpoint.best_revision, checkpoint.regression,
                                             str(journal.root / "checkpoint.json"))

    def _search(
        self,
        value: tuple[ProductionReductionRequest, ReductionCheckpoint],
        effects: tuple[ReductionJournal, ReductionRepository, ReductionTrial],
    ) -> ReductionCheckpoint:
        request, checkpoint = value
        journal, repository, trial = effects
        deps = self.dependencies
        while checkpoint.termination is None:
            if request.cancelled is not None and request.cancelled():
                return replace(checkpoint, termination="cancelled")
            if checkpoint.trials >= deps.policy.max_trials:
                return replace(checkpoint, termination="trial_budget_reached")
            if time.monotonic() >= repository.git.deadline:
                return replace(checkpoint, termination="deadline_reached")
            try:
                opportunity, limitations = _next_opportunity(
                    (deps.adapter, repository), checkpoint)
                checkpoint = replace(checkpoint, limitations=tuple(dict.fromkeys(
                    (*checkpoint.limitations, *limitations))))
                if opportunity is None:
                    return replace(checkpoint, termination="supported_opportunities_exhausted")
                digest = opportunity_digest((repository.sources(checkpoint.best_revision), opportunity))
                checkpoint = replace(checkpoint, trials=checkpoint.trials + 1,
                                     tried_ids=(*checkpoint.tried_ids, opportunity.transformation_id),
                                     tried_states=(*checkpoint.tried_states, digest))
                journal.save((checkpoint, deps.policy))
                replacement = opportunity.replacement
                journal.record((f"trial-{checkpoint.trials:04d}-proposal.json", {
                    "transformation_id": opportunity.transformation_id, "path": opportunity.path,
                    "description": opportunity.description, "source_revision": checkpoint.best_revision,
                    "replacement_sha256": None if replacement is None else hashlib.sha256(replacement).hexdigest(),
                    "replacement_deleted": replacement is None,
                }))
                if replacement is not None:
                    (journal.root / f"trial-{checkpoint.trials:04d}.source").write_bytes(replacement)
                result = trial.run(ReductionTrialRequest(
                    request, checkpoint.best_revision, opportunity, checkpoint.trials,
                    repository.git.deadline,
                ))
                checkpoint = replace(checkpoint, elapsed_seconds=checkpoint.elapsed_seconds + result.elapsed_seconds)
                if result.revision is not None:
                    checkpoint = replace(checkpoint, best_revision=result.revision,
                                         regression=result.regression, accepted=checkpoint.accepted + 1)
                journal.save((checkpoint, deps.policy))
            except ReductionDeadlineReached:
                journal.discard_pending((checkpoint.trials, "deadline_reached"))
                return replace(checkpoint, termination="deadline_reached")
        return checkpoint


def _next_opportunity(
    capabilities: tuple[ProductionReductionAdapter, ReductionRepository],
    checkpoint: ReductionCheckpoint,
) -> tuple[ReductionOpportunity | None, tuple[str, ...]]:
    adapter, repository = capabilities
    limitations: list[str] = []
    sources = repository.sources(checkpoint.best_revision)
    for source in sources:
        if source.baseline == source.candidate:
            continue
        plan = adapter.plan(source)
        limitations.extend(plan.limitations)
        for item in plan.opportunities:
            if item.path != source.path:
                raise ValueError("syntax capability proposed an unauthorized path")
            if item.replacement == source.candidate:
                continue
            if item.transformation_id in checkpoint.tried_ids:
                continue
            if opportunity_digest((sources, item)) not in checkpoint.tried_states:
                return item, tuple(limitations)
    return None, tuple(limitations)
