from __future__ import annotations

import json
from dataclasses import dataclass

from core.development.specification_gap_adapter import matching_contract_source_refs_for_clause
from core.development.tdd_progression import BehaviorContract, BehaviorContractRunState, ChecklistEvidence, ChecklistItemAssessment, SourceRequirementClause, SpecificationChecklistItem
from core.development.tdd_progression_values import ChecklistAssessmentStatus, ChecklistEvidenceKind, ChecklistItemKind
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


@dataclass(frozen=True)
class ChecklistEvidenceContext:
    item: SpecificationChecklistItem | SourceRequirementClause
    contract: BehaviorContract
    run_state: BehaviorContractRunState


@dataclass(frozen=True)
class EvidenceMappingRequest:
    project_id: str
    item: SpecificationChecklistItem | SourceRequirementClause
    candidates: list[ChecklistEvidence]


class AcceptedTestEvidenceCollector:
    """Collect accepted test evidence candidates for one checklist item."""

    def collect(self, context: ChecklistEvidenceContext) -> list[ChecklistEvidence]:
        matching_source_refs = matching_contract_source_refs_for_clause(context.contract, context.item)
        if not matching_source_refs:
            return []
        requirements = {requirement.ref: requirement for requirement in context.contract.observable_requirements}
        candidates: list[ChecklistEvidence] = []
        for cycle in context.run_state.cycles:
            if cycle.semantic_revision is None or cycle.red_phase is None or cycle.green_phase is None:
                continue
            for requirement_ref in cycle.step.requirement_refs:
                requirement = requirements.get(requirement_ref)
                if requirement is None or not matching_source_refs.intersection(requirement.source_refs):
                    continue
                candidates.append(
                    ChecklistEvidence(
                        checklist_ref=context.item.ref,
                        evidence_kind=ChecklistEvidenceKind.TEST.value,
                        test_name=cycle.step.test_name,
                        test_path=cycle.step.test_path,
                        step_id=cycle.step.step_id,
                        requirement_ref=requirement_ref,
                        accepted_revision=cycle.red_phase.accepted_revision,
                        semantic_revision=cycle.semantic_revision,
                        evidence_location=cycle.green_phase.evidence_location,
                        rationale=requirement.observable_outcome,
                    )
                )
        return candidates


class ApprovedReviewEvidenceCollector:
    """Collect semantically approved review evidence for one checklist item."""

    def collect(self, context: ChecklistEvidenceContext) -> list[ChecklistEvidence]:
        matching_source_refs = matching_contract_source_refs_for_clause(context.contract, context.item)
        if not matching_source_refs:
            return []
        requirements = {requirement.ref: requirement for requirement in context.contract.observable_requirements}
        evidence: list[ChecklistEvidence] = []
        for cycle in context.run_state.cycles:
            if cycle.semantic_revision is None or cycle.review_result is None:
                continue
            for requirement_ref in cycle.step.requirement_refs:
                requirement = requirements.get(requirement_ref)
                if requirement is None or not matching_source_refs.intersection(requirement.source_refs):
                    continue
                evidence.append(
                    ChecklistEvidence(
                        checklist_ref=context.item.ref,
                        evidence_kind=ChecklistEvidenceKind.REVIEW.value,
                        step_id=cycle.step.step_id,
                        requirement_ref=requirement_ref,
                        semantic_revision=cycle.semantic_revision,
                        evidence_location=cycle.green_phase.evidence_location if cycle.green_phase else None,
                        rationale=cycle.review_result.rationale,
                    )
                )
        return evidence


class ChecklistEvidenceMapper:
    """Map accepted test candidates to one checklist assessment through a narrow reasoning call."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def map(self, request: EvidenceMappingRequest) -> ChecklistItemAssessment:
        result = await self.gateway.reason(_mapping_request(request))
        payload = _json_object(result.text, label="checklist evidence mapping")
        status = str(payload.get("status"))
        rationale = str(payload.get("rationale", ""))
        selected_test_names = payload.get("selected_test_names", [])
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"unsupported checklist evidence mapping status: {status}")
        if not isinstance(selected_test_names, list):
            raise ValueError("selected_test_names must be a list")
        return _resolved_assessment(request.item.ref, status, rationale, request.candidates, selected_test_names)


_ALLOWED_STATUSES = {
    ChecklistAssessmentStatus.PROVEN.value,
    ChecklistAssessmentStatus.MISSING_TEST_EVIDENCE.value,
    ChecklistAssessmentStatus.UNCERTAIN.value,
}


def assessment_evidence_kind(item: SpecificationChecklistItem | SourceRequirementClause) -> str:
    if item.kind == ChecklistItemKind.QUALITY.value:
        return ChecklistEvidenceKind.REVIEW.value
    if item.kind == ChecklistItemKind.CONSTRAINT.value:
        return ChecklistEvidenceKind.MECHANICAL.value
    return ChecklistEvidenceKind.TEST.value


def _mapping_request(request: EvidenceMappingRequest) -> ReasoningRequest:
    return ReasoningRequest(
        purpose="athba_checklist_evidence_mapping",
        prompt=_evidence_mapping_prompt(item=request.item, candidates=request.candidates),
        project_id=request.project_id,
        requires_large_context=False,
    )


def _resolved_assessment(
    checklist_ref: str,
    status: str,
    rationale: str,
    candidates: list[ChecklistEvidence],
    selected_test_names: list[object],
) -> ChecklistItemAssessment:
    evidence_by_test = {candidate.test_name: candidate for candidate in candidates if candidate.test_name is not None}
    resolved: list[ChecklistEvidence] = []
    for test_name in [str(item) for item in selected_test_names]:
        evidence = evidence_by_test.get(test_name)
        if evidence is None:
            return ChecklistItemAssessment(
                checklist_ref=checklist_ref,
                status=ChecklistAssessmentStatus.UNCERTAIN.value,
                rationale="The evidence mapper referenced a test that does not exist in accepted TDD history.",
                evidence=[],
            )
        resolved.append(evidence)
    if status == ChecklistAssessmentStatus.PROVEN.value and not resolved:
        return ChecklistItemAssessment(
            checklist_ref=checklist_ref,
            status=ChecklistAssessmentStatus.UNCERTAIN.value,
            rationale="The evidence mapper claimed proof without accepted test evidence.",
            evidence=[],
        )
    return ChecklistItemAssessment(
        checklist_ref=checklist_ref,
        status=status,
        rationale=rationale,
        evidence=resolved,
    )


def _evidence_mapping_prompt(*, item: SpecificationChecklistItem | SourceRequirementClause, candidates: list[ChecklistEvidence]) -> str:
    return json.dumps(
        {
            "instruction": "Act as ATHBA's Specification Gatekeeper evidence mapper. Return raw JSON only.",
            "checklist_item": item.to_dict(),
            "accepted_test_candidates": [candidate.to_dict() for candidate in candidates],
            "required_output_schema": {
                "status": "proven|missing_test_evidence|uncertain",
                "rationale": "string",
                "selected_test_names": ["candidate test_name strings only"],
            },
            "rules": [
                "a checklist item is proven only when one or more accepted tests directly prove the obligation",
                "do not invent tests or evidence identifiers",
                "selected_test_names must be copied exactly from accepted_test_candidates",
                "if no candidate directly proves the obligation, return missing_test_evidence",
                "if a safe mapping cannot be established, return uncertain",
                "review or mechanical evidence is not allowed in this mapping call",
            ],
        },
        sort_keys=True,
    )


def _json_object(text: str, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return payload
