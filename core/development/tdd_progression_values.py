from __future__ import annotations

from enum import Enum


class TddPhase(str, Enum):
    RED = "red"
    GREEN = "green"
    COMPLETE = "complete"


class ContractPoolStatus(str, Enum):
    TDD_READY = "tdd_ready"
    CYCLE_ACTIVE = "cycle_active"
    REVIEW_READY = "review_ready"
    REPAIR_READY = "repair_ready"
    REPLAN_READY = "replan_ready"
    APPROVED = "approved"
    COMPLETED = "completed"
    BLOCKED_EXECUTOR = "blocked_executor"
    BLOCKED_ENVIRONMENT = "blocked_environment"
    BLOCKED_ARCHITECTURE = "blocked_architecture"
    BLOCKED_AMBIGUITY = "blocked_ambiguity"
    BLOCKED_UNCLASSIFIED = "blocked_unclassified"
    SPLIT_REQUIRED = "split_required"


class ReviewVerdict(str, Enum):
    APPROVED = "approved"
    REPAIR_REQUIRED = "repair_required"
    REPLAN_REQUIRED = "replan_required"


class StepDecisionStatus(str, Enum):
    PROPOSE = "propose"
    COMPLETE = "complete"


class ChecklistItemKind(str, Enum):
    BEHAVIOR = "behavior"
    VALIDATION = "validation"
    INVARIANT = "invariant"
    CONSTRAINT = "constraint"
    QUALITY = "quality"


class ChecklistEvidenceKind(str, Enum):
    TEST = "test"
    MECHANICAL = "mechanical"
    REVIEW = "review"


class ChecklistAssessmentStatus(str, Enum):
    PROVEN = "proven"
    MISSING_TEST_EVIDENCE = "missing_test_evidence"
    UNCERTAIN = "uncertain"


class GatekeeperAssessmentStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
