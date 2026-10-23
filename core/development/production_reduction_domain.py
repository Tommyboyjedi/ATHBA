"""Immutable inputs and bounded outcomes for deterministic change reduction."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.development.microcycle_domain import MaterialisedTestArtifact, RegressionState, ScenarioFragment
from core.development.required_public_signature import RequiredPublicSignature


@dataclass(frozen=True)
class ReductionPolicy:
    max_trials: int = 24
    max_seconds: float = 120.0

    def __post_init__(self) -> None:
        if self.max_trials < 0 or not 0 < self.max_seconds <= 120:
            raise ValueError("invalid reduction bounds")
        if self.max_trials > 24:
            raise ValueError("reduction trial bound exceeds qualified policy")


@dataclass(frozen=True)
class ReductionFrontierAuthority:
    artifact: MaterialisedTestArtifact
    active_fragment: ScenarioFragment
    prior_frontier_status: str | None
    test_path: str
    production_path: str


@dataclass(frozen=True)
class ProductionReductionRequest:
    repository_root: Path
    scenario_id: str
    frontier_index: int
    baseline_revision: str
    accepted_red_revision: str
    developer_input_revision: str
    candidate_revision: str
    production_paths: tuple[str, ...]
    current_frontier_test: str
    regression_command: tuple[str, ...]
    prior_completed_test_nodes: tuple[str, ...]
    include_accepted_suite: bool
    adapter_id: str
    frontier_authority: ReductionFrontierAuthority
    initial_regression: RegressionState
    required_artifacts: tuple[str, ...] = ()
    cancelled: Callable[[], bool] | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class ProductionReductionResult:
    revision: str
    regression: RegressionState
    evidence_ref: str


@dataclass(frozen=True)
class ReductionCheckpoint:
    identity: str
    best_revision: str
    regression: RegressionState
    deadline_unix: float
    trials: int = 0
    accepted: int = 0
    tried_ids: tuple[str, ...] = ()
    tried_states: tuple[str, ...] = ()
    elapsed_seconds: float = 0.0
    termination: str | None = None
    limitations: tuple[str, ...] = ()


class ReductionDeadlineReached(Exception):
    """An optional experiment cannot start or finish within its remaining bound."""


@dataclass(frozen=True)
class ContributionWindow:
    before_revision: str
    after_revision: str
    selected: bool


@dataclass(frozen=True)
class ContributionScope:
    windows: tuple[ContributionWindow, ...]
    protected_identifiers: tuple[RequiredPublicSignature, ...] = ()


@dataclass(frozen=True)
class ConsolidatedReductionRequest:
    """Already-approved completion authority, without a RED or Developer attempt."""
    repository_root: Path
    checkpoint_id: str
    baseline_revision: str
    tests_revision: str
    production_paths: tuple[str, ...]
    test_authorities: tuple[ReductionFrontierAuthority, ...]
    regression_command: tuple[str, ...]
    prior_completed_test_nodes: tuple[str, ...]
    adapter_id: str
    initial_regression: RegressionState
    required_artifacts: tuple[str, ...]
    scope: ContributionScope
    include_accepted_suite: bool = True
    cancelled: Callable[[], bool] | None = field(default=None, compare=False, repr=False)

    @property
    def candidate_revision(self) -> str:
        return self.tests_revision

    @property
    def current_frontier_test(self) -> str:
        if not self.test_authorities:
            raise ValueError("completion reduction requires approved test authority")
        return self.test_authorities[0].artifact.canonical_test_identity


ReductionRequest = ProductionReductionRequest | ConsolidatedReductionRequest
