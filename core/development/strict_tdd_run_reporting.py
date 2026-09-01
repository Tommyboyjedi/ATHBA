"""Persisted-evidence collection and report writing for strict-TDD runs."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from core.atomic_json_file import write_json_atomically
from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.microcycle_revision_store import MicrocycleRevisionRepository
from core.development.strict_tdd_feature_store import StrictTddFeatureRepository
from core.development.strict_tdd_lifecycle_evidence import (
    StrictTddLifecycleEventRepository,
    StrictTddLifecycleRunContext,
    StrictTddProofReportBuilder,
    StrictTddProofReportInput,
)
from core.development.strict_tdd_run_domain import StrictTddRunState
from core.filesystem_policy import resolve_identifier_path


@dataclass(frozen=True)
class StrictTddEvidenceRepositories:
    features: StrictTddFeatureRepository
    scenarios: ScenarioDraftStateRepo
    microcycles: MicrocycleStateRepo
    revisions: MicrocycleRevisionRepository
    lifecycle: StrictTddLifecycleEventRepository


class StrictTddRunEvidenceSnapshotCollector:
    def __init__(self, repositories: StrictTddEvidenceRepositories):
        self.repositories = repositories

    def collect(
        self,
        context: StrictTddLifecycleRunContext,
        state: StrictTddRunState,
    ) -> StrictTddProofReportInput:
        feature = self.repositories.features.load(state.project_id)
        scenario_ids = self._scenario_ids(feature, state)
        scenarios = tuple(
            scenario
            for scenario_id in scenario_ids
            if (scenario := self.repositories.scenarios.load(scenario_id)) is not None
        )
        microcycles = tuple(
            microcycle
            for scenario_id in scenario_ids
            if (microcycle := self.repositories.microcycles.load(scenario_id)) is not None
        )
        revisions = tuple(
            revision
            for scenario_id in scenario_ids
            if (revision := self.repositories.revisions.load(scenario_id)) is not None
        )
        return StrictTddProofReportInput(
            context,
            feature,
            scenarios,
            revisions,
            self.repositories.lifecycle.events(context),
            microcycles,
        )

    def _scenario_ids(self, feature: object, state: StrictTddRunState) -> tuple[str, ...]:
        values: list[str] = []
        if state.pending_transition_receipt is not None and state.pending_transition_receipt.scenario_id is not None:
            values.append(state.pending_transition_receipt.scenario_id)
        if feature is None:
            return tuple(dict.fromkeys(values))
        current = getattr(feature, "current_scenario_id")
        if current is not None:
            values.append(current)
        pending = getattr(feature, "pending_completed_behavior")
        if pending is not None:
            values.append(pending.scenario_id)
        values.extend(item.scenario_id for item in getattr(feature, "completed_behaviors"))
        return tuple(dict.fromkeys(values))


@dataclass(frozen=True)
class StrictTddRunReportPaths:
    structured: str
    markdown: str


class StrictTddRunReportWriter:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.builder = StrictTddProofReportBuilder()

    def write(self, run_id: str, input_value: StrictTddProofReportInput) -> StrictTddRunReportPaths:
        directory = resolve_identifier_path(self.root, run_id, "run id")
        structured = directory / "proof-report.json"
        markdown = directory / "proof-report.md"
        report = self.builder.build(input_value)
        write_json_atomically(structured, report.structured)
        _write_markdown(markdown, report.markdown)
        return StrictTddRunReportPaths(str(structured), str(markdown))


def _write_markdown(path: Path, value: str) -> None:
    temporary = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)