"""Compatibility facade for ATHBA TDD progression domain state."""

from core.development.behavior_contract_domain import (
    BehaviorContract,
    BehaviorContractLoadOptions,
    BehaviorContractRequirement,
)
from core.development.contract_run_domain import (
    BehaviorContractRunState,
    ContractCycleRecord,
    SemanticReviewResult,
    TddSnapshot,
    TddStepDecision,
    TddStepProposal,
)
from core.development.green_regression_domain import (
    RegressionDisposition,
    RegressionGateResult,
)
from core.development.semantic_progression_domain import (
    ObligationResolutionRecord,
    OpenSemanticObligation,
    ProvisionalRequirementState,
    SemanticObligationDraft,
    SemanticProgressLedger,
)
from core.development.red_acceptance import RedCandidateAnalysis
from core.development.specification_domain import (
    ChecklistEvidence,
    ChecklistItemAssessment,
    GatekeeperAssessmentRecord,
    SourceRequirementClause,
    SpecificationChecklist,
    SpecificationChecklistItem,
    SpecificationGap,
    SpecificationGatekeeperRunState,
)
from core.development.tdd_domain import (
    TddBehavior,
    TddBehaviorProgress,
    TddPhase,
    TddPhaseState,
    green_work_unit_id,
    red_work_unit_id,
    repair_work_unit_id,
)
from core.development.tdd_progression_values import (
    ChecklistAssessmentStatus,
    ChecklistEvidenceKind,
    ChecklistItemKind,
    ContractPoolStatus,
    GatekeeperAssessmentStatus,
    ReviewVerdict,
    StepDecisionStatus,
)

CONTRACT_POOL_STATUSES = {item.value for item in ContractPoolStatus}
REVIEW_VERDICTS = {item.value for item in ReviewVerdict}
STEP_DECISION_STATUSES = {item.value for item in StepDecisionStatus}
CHECKLIST_ITEM_KINDS = {item.value for item in ChecklistItemKind}
CHECKLIST_EVIDENCE_KINDS = {item.value for item in ChecklistEvidenceKind}
CHECKLIST_ASSESSMENT_STATUSES = {item.value for item in ChecklistAssessmentStatus}
GATEKEEPER_ASSESSMENT_STATUSES = {item.value for item in GatekeeperAssessmentStatus}

__all__ = [
    "BehaviorContract",
    "BehaviorContractLoadOptions",
    "BehaviorContractRequirement",
    "BehaviorContractRunState",
    "CHECKLIST_ASSESSMENT_STATUSES",
    "CHECKLIST_EVIDENCE_KINDS",
    "CHECKLIST_ITEM_KINDS",
    "CONTRACT_POOL_STATUSES",
    "ChecklistEvidence",
    "ChecklistItemAssessment",
    "ContractCycleRecord",
    "GATEKEEPER_ASSESSMENT_STATUSES",
    "GatekeeperAssessmentRecord",
    "REVIEW_VERDICTS",
    "RedCandidateAnalysis",
    "RegressionDisposition",
    "RegressionGateResult",
    "SemanticObligationDraft",
    "SemanticProgressLedger",
    "OpenSemanticObligation",
    "ProvisionalRequirementState",
    "ObligationResolutionRecord",
    "SemanticReviewResult",
    "SourceRequirementClause",
    "SpecificationChecklist",
    "SpecificationChecklistItem",
    "SpecificationGap",
    "SpecificationGatekeeperRunState",
    "TddBehavior",
    "TddBehaviorProgress",
    "TddPhase",
    "TddPhaseState",
    "TddSnapshot",
    "STEP_DECISION_STATUSES",
    "TddStepDecision",
    "TddStepProposal",
    "green_work_unit_id",
    "red_work_unit_id",
    "repair_work_unit_id",
]
