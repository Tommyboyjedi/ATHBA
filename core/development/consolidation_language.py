"""Reuse configured test syntax and structured execution without a fabricated RED."""
from __future__ import annotations

from dataclasses import dataclass

from core.development.microcycle_domain import (
    FinalTestMaterialisationRequest, FragmentationRequest, LanguageTestAdapter,
    ScenarioModel, ScenarioParseRequest, ScenarioSourceCandidate, SyntaxValidationRequest,
    TestScenarioDraft,
)
from core.development.production_reduction_domain import ReductionFrontierAuthority
from core.development.test_material import TestMaterialAdapter
from core.development.scenario_drafting import _authoring_contract
from core.development.scenario_drafting_domain import ScenarioAuthoringIdentity, ScenarioCandidateAssessmentRequest


@dataclass(frozen=True)
class ConsolidationTestSource:
    checkpoint_id: str
    identity: str
    source: str
    production_path: str
    revision: str


class ConsolidationLanguage:
    """Validate one ordinary replacement and expose opaque original fragments."""

    def __init__(self, adapter: LanguageTestAdapter, material: TestMaterialAdapter):
        self.adapter = adapter
        self.material = material

    def model(self, request: ConsolidationTestSource) -> ScenarioModel:
        draft = TestScenarioDraft(
            request.checkpoint_id, request.checkpoint_id,
            self.adapter.descriptor.language_id, request.source, request.identity,
            self.material.test_path(request.identity),
            scenario_rationale="Approved replacement evidence; no new TDD cycle",
        )
        model = self.adapter.parse_scenario(ScenarioParseRequest(draft))
        if not self.adapter.validate_scenario_syntax(SyntaxValidationRequest(model)):
            raise ValueError("unsupported consolidation test syntax")
        return model

    def validate(self, request: ConsolidationTestSource) -> tuple[str, ReductionFrontierAuthority]:
        path = self.material.test_path(request.identity)
        candidate = ScenarioSourceCandidate(
            request.checkpoint_id, request.checkpoint_id, self.adapter.descriptor.language_id,
            path, request.source, request.identity, request.revision, request.checkpoint_id,
        )
        canonical = self.adapter.canonicalise_candidate(candidate, request.identity)
        assessor = getattr(self.adapter, "assess_candidate", None)
        if assessor is None:
            raise ValueError("consolidation authoring capability is unavailable")
        assessment = assessor(ScenarioCandidateAssessmentRequest(
            canonical, request.production_path, self.authoring_contract()))
        if not assessment.accepted:
            raise ValueError(assessment.repair_feedback())
        analysis = self.adapter.analyse_candidate(canonical, request.production_path)
        if analysis.rejection_feedback():
            raise ValueError(analysis.rejection_feedback())
        authority = self.authority(ConsolidationTestSource(
            request.checkpoint_id, request.identity, canonical.source,
            request.production_path, request.revision,
        ))
        return canonical.source, authority

    def authority(self, request: ConsolidationTestSource) -> ReductionFrontierAuthority:
        model = self.model(request)
        fragments = self.adapter.fragment_scenario(FragmentationRequest(model))
        artifact = self.adapter.materialise_final_test(
            FinalTestMaterialisationRequest(model, fragments, request.revision))
        active = next(item for item in fragments if item.fragment_id == artifact.active_fragment_id)
        return ReductionFrontierAuthority(
            artifact, active, None, self.material.test_path(request.identity), request.production_path,
        )

    def observation_refs(self, request: ConsolidationTestSource) -> tuple[tuple[str, str], ...]:
        model = self.model(request)
        fragments = self.adapter.fragment_scenario(FragmentationRequest(model))
        return tuple((item.fragment_id, item.source) for item in fragments)

    def authoring_contract(self):
        return _authoring_contract(ScenarioAuthoringIdentity(
            self.adapter.descriptor.language_id, self.adapter.framework_id))
