"""Bounded partner selection and immutable completed authority for consolidation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from core.datastore.repos.microcycle_state_repo import MicrocycleStateRepo
from core.datastore.repos.scenario_draft_state_repo import ScenarioDraftStateRepo
from core.development.behavior_contract_domain import BehaviorContract
from core.development.consolidation_evidence import (
    ActiveAcceptedEvidenceResolver, ActiveEvidenceRequest, CaseSnapshot,
)
from core.development.consolidation_language import ConsolidationLanguage, ConsolidationTestSource
from core.development.consolidation_reasoning import (
    ConsolidationReasoningContext, MAX_CONSOLIDATION_CONTEXT_BYTES,
)
from core.development.production_reduction_domain import ContributionScope, ContributionWindow
from core.development.project_environment import DevelopmentProject
from core.development.specification_reconciliation import (
    AcceptedTestEvidence, CompletedMicrocycleEvidenceCollector, GitAcceptedTestCatalog,
    TestCatalogRevision,
)
from core.development.strict_tdd_feature_domain import StrictTddFeatureState
from core.development.test_material import TestMaterialAdapter

MAX_CONSOLIDATED_MEMBERS = 8


@dataclass(frozen=True)
class ConsolidationContext:
    state: StrictTddFeatureState
    project: DevelopmentProject


@dataclass(frozen=True)
class SelectedConsolidation:
    member_refs: tuple[str, ...]
    previous_tests: tuple[CaseSnapshot, ...]
    unaffected_tests: tuple[str, ...]
    reasoning: ConsolidationReasoningContext
    scope: ContributionScope
    production_paths: tuple[str, ...]


@dataclass(frozen=True)
class ConsolidationMaterialDependencies:
    repository_root: Path
    microcycles: MicrocycleStateRepo
    drafts: ScenarioDraftStateRepo
    test_material: TestMaterialAdapter
    language: ConsolidationLanguage


class ConsolidationMaterial:
    """Select at most one related active group; wording never establishes equivalence."""

    def __init__(self, dependencies: ConsolidationMaterialDependencies):
        self.dependencies = dependencies

    def prepare(self, request: tuple[ConsolidationContext, str]) -> SelectedConsolidation | None:
        context, identity = request
        state = context.state
        contract = BehaviorContract.from_dict(dict(state.contract_payload or {}))
        if len(contract.production_paths) != 1:
            return None
        active = self._active(state)
        newest = state.completed_behaviors[-1].behavior_ref
        current = tuple(item for item in active if newest in _members(item))
        if len(current) != 1 or len(_members(current[0])) != 1:
            raise ValueError("newly completed behavior has ambiguous active evidence")
        requirements = {item.ref: item for item in contract.observable_requirements}
        selected_requirement = requirements[newest]
        partner = next((item for item in reversed(active) if item not in current and (
            set(selected_requirement.depends_on) & set(_members(item))
            or set(selected_requirement.source_refs) & set(item.requirement_refs))), None)
        if partner is None:
            return None
        members = tuple(dict.fromkeys((*_members(partner), newest)))
        selected = tuple(item for item in active if set(_members(item)).issubset(members))
        if len(members) > MAX_CONSOLIDATED_MEMBERS or len({item.test_path for item in selected}) != 1:
            return None
        catalog = GitAcceptedTestCatalog(self.dependencies.repository_root,
            TestCatalogRevision(str(state.canonical_development_base), self.dependencies.test_material))
        cases = tuple(_snapshot(item, catalog) for item in selected)
        semantic, refs = self._semantic((contract, cases), identity)
        if len(semantic.encode()) > MAX_CONSOLIDATION_CONTEXT_BYTES:
            return None
        reasoning = ConsolidationReasoningContext(identity, state.project_id, semantic, refs, current[0].test_name)
        return SelectedConsolidation(members, cases,
            tuple(item.test_name for item in active if item not in selected), reasoning,
            self._scope((state, members), contract), tuple(contract.production_paths))

    def _active(self, state: StrictTddFeatureState) -> tuple[AcceptedTestEvidence, ...]:
        states = tuple(self.dependencies.microcycles.load(item.scenario_id) for item in state.completed_behaviors)
        if any(item is None for item in states):
            raise ValueError("completed consolidation source state is unavailable")
        originals = CompletedMicrocycleEvidenceCollector().collect(tuple(item for item in states if item is not None))
        if len(originals) != len(states):
            raise ValueError("consolidation requires fully reviewed completed requirements")
        return ActiveAcceptedEvidenceResolver(self.dependencies.repository_root,
            self.dependencies.test_material).resolve(ActiveEvidenceRequest(
                tuple(originals), state.evidence_consolidations, str(state.canonical_development_base)))

    def _semantic(self, request: tuple[BehaviorContract, tuple[CaseSnapshot, ...]],
                  identity: str) -> tuple[str, tuple[str, ...]]:
        contract, cases = request
        members = tuple(dict.fromkeys(ref for case in cases for ref in case.requirement_refs))
        refs = list(members)
        observations = []
        for case in cases:
            refs.append(case.observation_ref)
            fragments = self.dependencies.language.observation_refs(ConsolidationTestSource(
                identity, case.name, case.source, contract.production_paths[0], case.revision))
            for key, source in fragments:
                ref = f"fragment:{case.source_hash}:{key}"
                refs.append(ref)
                observations.append({"ref": ref, "source": source, "test": case.name})
        source_refs = {ref for case in cases for ref in case.source_refs}
        payload = {
            "obligations": [item.to_dict() for item in contract.observable_requirements if item.ref in members],
            "source_authority": [item.to_dict() for item in contract.source_clauses if item.ref in source_refs],
            "accepted_tests": [case.to_dict() for case in cases], "observations": observations,
            "repository_facts": {"production_path": contract.production_paths[0], "test_path": cases[0].path},
            "authoring_contract": self.dependencies.language.authoring_contract().to_dict(),
            "language": self.dependencies.language.adapter.descriptor.language_id,
            "framework": self.dependencies.test_material.framework,
        }
        return json.dumps(payload, sort_keys=True), tuple(dict.fromkeys(refs))

    def _scope(self, selection: tuple[StrictTddFeatureState, tuple[str, ...]],
               contract: BehaviorContract) -> ContributionScope:
        state, members = selection
        windows = []
        for completed in state.completed_behaviors:
            draft = self.dependencies.drafts.load(completed.scenario_id)
            if draft is None:
                raise ValueError("consolidation contribution has no immutable initial base")
            windows.append(ContributionWindow(draft.development_base_revision,
                completed.canonical_revision, completed.behavior_ref in members))
            for record in state.evidence_consolidations:
                if record.production_revision == completed.canonical_revision:
                    windows.append(ContributionWindow(record.production_revision, record.final_revision,
                        set(record.member_refs).issubset(members)))
        return ContributionScope(tuple(windows), tuple(contract.required_signatures))


def _members(item: AcceptedTestEvidence) -> tuple[str, ...]:
    return item.covered_requirement_refs or (item.step_id,)


def _snapshot(item: AcceptedTestEvidence, catalog: GitAcceptedTestCatalog) -> CaseSnapshot:
    source = catalog.verified_source(item)
    if source is None:
        raise ValueError("accepted consolidation source changed without authority")
    return CaseSnapshot(item.test_name, item.test_path, source, item.semantic_revision,
                        _members(item), tuple(item.requirement_refs))


def checkpoint_identity(state: StrictTddFeatureState) -> str:
    completed = state.completed_behaviors[-1]
    key = f"{state.project_id}:{state.source_requirement_hash}:{completed.scenario_id}:{completed.canonical_revision}"
    return hashlib.sha256(key.encode()).hexdigest()
