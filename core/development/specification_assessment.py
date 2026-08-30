from __future__ import annotations

from dataclasses import dataclass, replace

from core.development.specification_atomization import ChecklistAtomizationRequest, SpecificationChecklistPlanner
from core.development.specification_evidence import AcceptedTestEvidenceCollector, ApprovedReviewEvidenceCollector, ChecklistEvidenceContext, ChecklistEvidenceMapper, EvidenceMappingRequest, assessment_evidence_kind
from core.development.tdd_progression import BehaviorContract, BehaviorContractRunState, ChecklistItemAssessment, GatekeeperAssessmentRecord, SpecificationGap, SpecificationGatekeeperRunState
from core.development.tdd_progression_values import ChecklistAssessmentStatus, ChecklistEvidenceKind, GatekeeperAssessmentStatus
from core.execution.reasoning_gateway import ReasoningGateway


@dataclass(frozen=True)
class GatekeeperStateRequest:
    contract: BehaviorContract
    gatekeeper_state: SpecificationGatekeeperRunState | None


@dataclass(frozen=True)
class GatekeeperAssessmentRequest:
    contract: BehaviorContract
    run_state: BehaviorContractRunState
    gatekeeper_state: SpecificationGatekeeperRunState


@dataclass(frozen=True)
class ChecklistAssessmentContext:
    item: object
    contract: BehaviorContract
    run_state: BehaviorContractRunState


class ChecklistItemAssessor:
    """Assess one checklist item using deterministic evidence collection and narrow mapping calls."""

    def __init__(self, gateway: ReasoningGateway):
        self.test_collector = AcceptedTestEvidenceCollector()
        self.review_collector = ApprovedReviewEvidenceCollector()
        self.mapper = ChecklistEvidenceMapper(gateway)

    async def assess(self, context: ChecklistAssessmentContext) -> ChecklistItemAssessment:
        item_context = ChecklistEvidenceContext(context.item, context.contract, context.run_state)
        evidence_kind = assessment_evidence_kind(context.item)
        if evidence_kind == ChecklistEvidenceKind.REVIEW.value:
            return _review_assessment(context.item.ref, self.review_collector.collect(item_context))
        if evidence_kind == ChecklistEvidenceKind.MECHANICAL.value:
            return _mechanical_assessment(context.item.ref)
        candidates = self.test_collector.collect(item_context)
        if not candidates:
            return _missing_test_assessment(context.item.ref)
        return await self.mapper.map(EvidenceMappingRequest(context.contract.project_id, context.item, candidates))


class GatekeeperAssessmentRunner:
    """Build one complete gatekeeper assessment snapshot."""

    def __init__(self, item_assessor: ChecklistItemAssessor):
        self.item_assessor = item_assessor

    async def assess(self, request: GatekeeperAssessmentRequest) -> SpecificationGatekeeperRunState:
        item_assessments: list[ChecklistItemAssessment] = []
        gaps: list[SpecificationGap] = []
        for item in request.gatekeeper_state.checklist.items:
            assessment = await self.item_assessor.assess(ChecklistAssessmentContext(item, request.contract, request.run_state))
            item_assessments.append(assessment)
            if assessment.status != ChecklistAssessmentStatus.PROVEN.value:
                gaps.append(_gap_from_assessment(item, assessment))
        status = GatekeeperAssessmentStatus.COMPLETE.value if all(
            item.status == ChecklistAssessmentStatus.PROVEN.value for item in item_assessments
        ) else GatekeeperAssessmentStatus.INCOMPLETE.value
        record = GatekeeperAssessmentRecord(status=status, item_assessments=item_assessments, gaps=gaps)
        return replace(
            request.gatekeeper_state,
            latest_assessment=record,
            assessment_history=[*request.gatekeeper_state.assessment_history, record],
        )


class SpecificationGatekeeper:
    """Coordinate checklist state creation and full checklist assessment."""

    def __init__(self, gateway: ReasoningGateway, checklist_planner: SpecificationChecklistPlanner | None = None):
        self.checklist_planner = checklist_planner or SpecificationChecklistPlanner(gateway)
        self.runner = GatekeeperAssessmentRunner(ChecklistItemAssessor(gateway))

    async def ensure_state(self, request: GatekeeperStateRequest) -> SpecificationGatekeeperRunState:
        if request.gatekeeper_state is not None:
            return request.gatekeeper_state
        checklist = await self.checklist_planner.create_checklist(
            ChecklistAtomizationRequest(
                project_id=request.contract.project_id,
                requirement_text=request.contract.requirement_source,
            )
        )
        return SpecificationGatekeeperRunState(checklist=checklist)

    async def assess(self, request: GatekeeperAssessmentRequest) -> SpecificationGatekeeperRunState:
        return await self.runner.assess(request)


def _gap_from_assessment(item: object, assessment: ChecklistItemAssessment) -> SpecificationGap:
    return SpecificationGap(
        checklist_ref=item.ref,
        obligation_text=item.text,
        item_kind=item.kind,
        reason=assessment.rationale,
        desired_proof=f"Add accepted executable proof for: {item.text}",
        related_test_names=[evidence.test_name for evidence in assessment.evidence if evidence.test_name is not None],
    )


def _review_assessment(checklist_ref: str, evidence: list[object]) -> ChecklistItemAssessment:
    if evidence:
        return ChecklistItemAssessment(
            checklist_ref=checklist_ref,
            status=ChecklistAssessmentStatus.PROVEN.value,
            rationale="Semantically approved review evidence exists for this quality obligation.",
            evidence=evidence,
        )
    return ChecklistItemAssessment(
        checklist_ref=checklist_ref,
        status=ChecklistAssessmentStatus.UNCERTAIN.value,
        rationale="No semantically approved review evidence was available for this quality obligation.",
        evidence=[],
    )


def _mechanical_assessment(checklist_ref: str) -> ChecklistItemAssessment:
    return ChecklistItemAssessment(
        checklist_ref=checklist_ref,
        status=ChecklistAssessmentStatus.UNCERTAIN.value,
        rationale="No deterministic mechanical proof has been attached for this checklist item yet.",
        evidence=[],
    )


def _missing_test_assessment(checklist_ref: str) -> ChecklistItemAssessment:
    return ChecklistItemAssessment(
        checklist_ref=checklist_ref,
        status=ChecklistAssessmentStatus.MISSING_TEST_EVIDENCE.value,
        rationale="No accepted semantically approved pytest evidence currently proves this obligation.",
        evidence=[],
    )
