from __future__ import annotations

import json
from dataclasses import replace

from core.development.tdd_progression import (
    BehaviorContract,
    BehaviorContractRequirement,
    BehaviorContractRunState,
    ChecklistEvidence,
    ChecklistItemAssessment,
    GatekeeperAssessmentRecord,
    SourceRequirementClause,
    SpecificationChecklist,
    SpecificationGap,
    SpecificationGatekeeperRunState,
)
from core.execution.reasoning_gateway import ReasoningGateway, ReasoningRequest


class SpecificationChecklistPlanner:
    """Create an independent specification checklist from one component requirement."""

    def __init__(self, gateway: ReasoningGateway):
        self.gateway = gateway

    async def create_checklist(self, *, project_id: str, requirement_text: str) -> SpecificationChecklist:
        request = ReasoningRequest(
            purpose="athba_specification_checklist",
            prompt=_checklist_prompt(project_id=project_id, requirement_text=requirement_text),
            project_id=project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        payload = _json_object(result.text, label="specification checklist")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("specification checklist response must include an items list")
        return SpecificationChecklist(
            project_id=project_id,
            requirement_text=requirement_text,
            items=[SourceRequirementClause.from_dict(dict(item)) for item in raw_items],
        )


class SpecificationGapTddAdapter:
    """Turn one targeted specification gap into one supplemental contract requirement."""

    def extend_contract_for_gap(self, contract: BehaviorContract, gap: SpecificationGap) -> BehaviorContract:
        prefix = f"GK-{gap.checklist_ref}-"
        if any(requirement.ref.startswith(prefix) for requirement in contract.observable_requirements):
            return contract
        requirement = BehaviorContractRequirement(
            ref=_next_gap_requirement_ref(contract, gap.checklist_ref),
            source_refs=[gap.checklist_ref],
            summary=gap.obligation_text,
            observable_outcome=gap.desired_proof,
            test_hint=gap.desired_proof,
            error_expectation="Add executable proof for the missing validation outcome." if gap.item_kind == "validation" else None,
            preserves_state_on_failure=gap.item_kind in {"validation", "invariant", "constraint"},
        )
        return replace(
            contract,
            observable_requirements=[*contract.observable_requirements, requirement],
        )


class SpecificationGatekeeper:
    """Assess whether accepted evidence proves each independent checklist item."""

    def __init__(self, gateway: ReasoningGateway, checklist_planner: SpecificationChecklistPlanner | None = None):
        self.gateway = gateway
        self.checklist_planner = checklist_planner or SpecificationChecklistPlanner(gateway)

    async def ensure_state(
        self,
        contract: BehaviorContract,
        gatekeeper_state: SpecificationGatekeeperRunState | None,
    ) -> SpecificationGatekeeperRunState:
        if gatekeeper_state is not None:
            return gatekeeper_state
        checklist = await self.checklist_planner.create_checklist(
            project_id=contract.project_id,
            requirement_text=contract.requirement_source,
        )
        return SpecificationGatekeeperRunState(checklist=checklist)

    async def assess(
        self,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        gatekeeper_state: SpecificationGatekeeperRunState,
    ) -> SpecificationGatekeeperRunState:
        item_assessments: list[ChecklistItemAssessment] = []
        gaps: list[SpecificationGap] = []
        for item in gatekeeper_state.checklist.items:
            assessment = await self._assess_item(item, contract, run_state)
            item_assessments.append(assessment)
            if assessment.status != "proven":
                gaps.append(
                    SpecificationGap(
                        checklist_ref=item.ref,
                        obligation_text=item.text,
                        item_kind=item.kind,
                        reason=assessment.rationale,
                        desired_proof=f"Add accepted executable proof for: {item.text}",
                        related_test_names=[evidence.test_name for evidence in assessment.evidence if evidence.test_name is not None],
                    )
                )
        status = "complete" if all(item.status == "proven" for item in item_assessments) else "incomplete"
        record = GatekeeperAssessmentRecord(status=status, item_assessments=item_assessments, gaps=gaps)
        return replace(
            gatekeeper_state,
            latest_assessment=record,
            assessment_history=[*gatekeeper_state.assessment_history, record],
        )

    async def _assess_item(
        self,
        item: SourceRequirementClause,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
    ) -> ChecklistItemAssessment:
        if item.evidence_kind == "review":
            evidence = self._approved_review_candidates(contract, run_state, item.ref)
            if evidence:
                return ChecklistItemAssessment(
                    checklist_ref=item.ref,
                    status="proven",
                    rationale="Semantically approved review evidence exists for this quality obligation.",
                    evidence=evidence,
                )
            return ChecklistItemAssessment(
                checklist_ref=item.ref,
                status="uncertain",
                rationale="No semantically approved review evidence was available for this quality obligation.",
                evidence=[],
            )
        if item.evidence_kind == "mechanical":
            return ChecklistItemAssessment(
                checklist_ref=item.ref,
                status="uncertain",
                rationale="No deterministic mechanical proof has been attached for this checklist item yet.",
                evidence=[],
            )

        candidates = self._accepted_test_candidates(contract, run_state, item.ref)
        if not candidates:
            return ChecklistItemAssessment(
                checklist_ref=item.ref,
                status="missing_test_evidence",
                rationale="No accepted semantically approved pytest evidence currently proves this obligation.",
                evidence=[],
            )

        request = ReasoningRequest(
            purpose="athba_checklist_evidence_mapping",
            prompt=_evidence_mapping_prompt(item=item, candidates=candidates),
            project_id=contract.project_id,
            requires_large_context=False,
        )
        result = await self.gateway.reason(request)
        payload = _json_object(result.text, label="checklist evidence mapping")
        status = str(payload.get("status"))
        rationale = str(payload.get("rationale", ""))
        selected_test_names = payload.get("selected_test_names", [])
        if status not in {"proven", "missing_test_evidence", "uncertain"}:
            raise ValueError(f"unsupported checklist evidence mapping status: {status}")
        if not isinstance(selected_test_names, list):
            raise ValueError("selected_test_names must be a list")
        normalized_selected = [str(item) for item in selected_test_names]
        evidence_by_test = {candidate.test_name: candidate for candidate in candidates if candidate.test_name is not None}
        resolved: list[ChecklistEvidence] = []
        for test_name in normalized_selected:
            evidence = evidence_by_test.get(test_name)
            if evidence is None:
                return ChecklistItemAssessment(
                    checklist_ref=item.ref,
                    status="uncertain",
                    rationale="The evidence mapper referenced a test that does not exist in accepted TDD history.",
                    evidence=[],
                )
            resolved.append(evidence)
        if status == "proven" and not resolved:
            return ChecklistItemAssessment(
                checklist_ref=item.ref,
                status="uncertain",
                rationale="The evidence mapper claimed proof without accepted test evidence.",
                evidence=[],
            )
        return ChecklistItemAssessment(
            checklist_ref=item.ref,
            status=status,
            rationale=rationale,
            evidence=resolved,
        )

    def _accepted_test_candidates(
        self,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        checklist_ref: str,
    ) -> list[ChecklistEvidence]:
        requirements = {requirement.ref: requirement for requirement in contract.observable_requirements}
        candidates: list[ChecklistEvidence] = []
        for cycle in run_state.cycles:
            if cycle.semantic_revision is None or cycle.red_phase is None or cycle.green_phase is None:
                continue
            for requirement_ref in cycle.step.requirement_refs:
                requirement = requirements.get(requirement_ref)
                if requirement is None or checklist_ref not in requirement.source_refs:
                    continue
                candidates.append(
                    ChecklistEvidence(
                        checklist_ref=checklist_ref,
                        evidence_kind="test",
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

    def _approved_review_candidates(
        self,
        contract: BehaviorContract,
        run_state: BehaviorContractRunState,
        checklist_ref: str,
    ) -> list[ChecklistEvidence]:
        requirements = {requirement.ref: requirement for requirement in contract.observable_requirements}
        evidence: list[ChecklistEvidence] = []
        for cycle in run_state.cycles:
            if cycle.semantic_revision is None or cycle.review_result is None:
                continue
            for requirement_ref in cycle.step.requirement_refs:
                requirement = requirements.get(requirement_ref)
                if requirement is None or checklist_ref not in requirement.source_refs:
                    continue
                evidence.append(
                    ChecklistEvidence(
                        checklist_ref=checklist_ref,
                        evidence_kind="review",
                        step_id=cycle.step.step_id,
                        requirement_ref=requirement_ref,
                        semantic_revision=cycle.semantic_revision,
                        evidence_location=cycle.green_phase.evidence_location if cycle.green_phase else None,
                        rationale=cycle.review_result.rationale,
                    )
                )
        return evidence


def _next_gap_requirement_ref(contract: BehaviorContract, checklist_ref: str) -> str:
    prefix = f"GK-{checklist_ref}-"
    existing = {requirement.ref for requirement in contract.observable_requirements}
    counter = 1
    while f"{prefix}{counter}" in existing:
        counter += 1
    return f"{prefix}{counter}"


def _json_object(text: str, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} response was not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} response must be a JSON object")
    return payload


def _checklist_prompt(*, project_id: str, requirement_text: str) -> str:
    return json.dumps(
        {
            "instruction": "Act as ATHBA's Specification Gatekeeper atomizer. Return raw JSON only.",
            "project_id": project_id,
            "requirement_text": requirement_text,
            "output_rules": [
                "return raw JSON only",
                "do not wrap the JSON in Markdown",
                "do not use code fences",
                "do not add commentary before or after the JSON",
                "include exactly one top-level items array",
                "do not add extra fields outside the required schema",
            ],
            "required_output_schema": {
                "items": [
                    {
                        "ref": "string",
                        "text": "string",
                        "kind": "behavior|validation|invariant|constraint|quality",
                        "evidence_kind": "test|mechanical|review",
                    }
                ]
            },
            "rules": [
                "one semantic obligation per item",
                "preserve happy paths",
                "preserve failure cases",
                "preserve invariants",
                "preserve constraints",
                "preserve explicit quality and non-functional requirements where applicable",
                "do not invent unrelated requirements",
                "do not merge distinct behaviors simply because they appear in the same sentence",
                "kind must be one of behavior, validation, invariant, constraint, quality",
                "evidence_kind must be one of test, mechanical, review",
                "use test for executable behavior and validation obligations by default",
                "use review for readability and unnecessary-abstraction obligations",
                "use mechanical for deterministic environment and dependency constraints",
                "do not include worker ids, model ids, GPU ids, endpoints, or ports",
            ],
        },
        indent=2,
        sort_keys=True,
    )


def _evidence_mapping_prompt(*, item: SourceRequirementClause, candidates: list[ChecklistEvidence]) -> str:
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
                "do not use production source inspection as proof",
            ],
        },
        indent=2,
        sort_keys=True,
    )
