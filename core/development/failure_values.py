from __future__ import annotations

from enum import Enum


class FailureClassification(str, Enum):
    EXECUTOR_INFRASTRUCTURE_FAILURE = "executor_infrastructure_failure"
    ENVIRONMENT_FAILURE = "environment_failure"
    RESOURCE_LIMIT_FAILURE = "resource_limit_failure"
    SYNTAX_OR_PARSE_FAILURE = "syntax_or_parse_failure"
    BUILD_OR_LINK_FAILURE = "build_or_link_failure"
    TEST_COLLECTION_OR_BOOTSTRAP_FAILURE = "test_collection_or_bootstrap_failure"
    SECURITY_OR_EXECUTION_POLICY_VIOLATION = "security_or_execution_policy_violation"
    CHANGE_SCOPE_VIOLATION = "change_scope_violation"
    DEPENDENCY_OR_PREREQUISITE_FAILURE = "dependency_or_prerequisite_failure"
    CONTRACT_OR_REQUIREMENT_AMBIGUITY = "contract_or_requirement_ambiguity"
    TESTER_CANDIDATE_DEFECT = "tester_candidate_defect"
    DEVELOPER_CANDIDATE_DEFECT = "developer_candidate_defect"
    EXPECTED_BEHAVIOR_RED = "expected_behavior_red"
    ACCUMULATED_REGRESSION = "accumulated_regression"
    SEMANTIC_INTEGRATION_FAILURE = "semantic_integration_failure"
    REVIEW_QUALITY_FAILURE = "review_quality_failure"
    ARCHITECTURE_CONSTRAINT_VIOLATION = "architecture_constraint_violation"
    UNCLASSIFIED_FAILURE = "unclassified_failure"


FAILURE_PRIORITY = {
    classification: index for index, classification in enumerate(FailureClassification, start=1)
}


class ProgressionAction(str, Enum):
    BLOCK_EXECUTOR = "block_executor"
    RECOVER_ENVIRONMENT = "recover_environment"
    SPLIT_PACKET = "split_packet"
    ASSESS_MECHANICAL_DEPENDENCY = "assess_mechanical_dependency"
    REPAIR_TESTER = "repair_tester"
    REPAIR_DEVELOPER = "repair_developer"
    REPLAN_DEPENDENCY = "replan_dependency"
    BLOCK_AMBIGUITY = "block_ambiguity"
    ACCEPT_RED = "accept_red"
    REPAIR_REGRESSION = "repair_regression"
    REPLAN_INTEGRATION = "replan_integration"
    REPAIR_REVIEW = "repair_review"
    BLOCK_ARCHITECTURE = "block_architecture"
    ANALYZE_UNCLASSIFIED = "analyze_unclassified"


FAILURE_ACTIONS = {
    FailureClassification.EXECUTOR_INFRASTRUCTURE_FAILURE: ProgressionAction.BLOCK_EXECUTOR,
    FailureClassification.ENVIRONMENT_FAILURE: ProgressionAction.RECOVER_ENVIRONMENT,
    FailureClassification.RESOURCE_LIMIT_FAILURE: ProgressionAction.SPLIT_PACKET,
    FailureClassification.SYNTAX_OR_PARSE_FAILURE: ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY,
    FailureClassification.BUILD_OR_LINK_FAILURE: ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY,
    FailureClassification.TEST_COLLECTION_OR_BOOTSTRAP_FAILURE: ProgressionAction.ASSESS_MECHANICAL_DEPENDENCY,
    FailureClassification.SECURITY_OR_EXECUTION_POLICY_VIOLATION: ProgressionAction.REPAIR_TESTER,
    FailureClassification.CHANGE_SCOPE_VIOLATION: ProgressionAction.REPAIR_TESTER,
    FailureClassification.DEPENDENCY_OR_PREREQUISITE_FAILURE: ProgressionAction.REPLAN_DEPENDENCY,
    FailureClassification.CONTRACT_OR_REQUIREMENT_AMBIGUITY: ProgressionAction.BLOCK_AMBIGUITY,
    FailureClassification.TESTER_CANDIDATE_DEFECT: ProgressionAction.REPAIR_TESTER,
    FailureClassification.DEVELOPER_CANDIDATE_DEFECT: ProgressionAction.REPAIR_DEVELOPER,
    FailureClassification.EXPECTED_BEHAVIOR_RED: ProgressionAction.ACCEPT_RED,
    FailureClassification.ACCUMULATED_REGRESSION: ProgressionAction.REPAIR_REGRESSION,
    FailureClassification.SEMANTIC_INTEGRATION_FAILURE: ProgressionAction.REPLAN_INTEGRATION,
    FailureClassification.REVIEW_QUALITY_FAILURE: ProgressionAction.REPAIR_REVIEW,
    FailureClassification.ARCHITECTURE_CONSTRAINT_VIOLATION: ProgressionAction.BLOCK_ARCHITECTURE,
    FailureClassification.UNCLASSIFIED_FAILURE: ProgressionAction.ANALYZE_UNCLASSIFIED,
}


class FailureRouteState(str, Enum):
    ACTIVE = "active"
    AWAITING_REPAIR = "awaiting_repair"
    DEFERRED_DEPENDENCY = "deferred_dependency"
    AWAITING_PREREQUISITE = "awaiting_prerequisite"
    AWAITING_ENVIRONMENT_RECOVERY = "awaiting_environment_recovery"
    AWAITING_SPLIT = "awaiting_split"
    BLOCKED_EXECUTOR = "blocked_executor"
    BLOCKED_ARCHITECTURE = "blocked_architecture"
    BLOCKED_AMBIGUITY = "blocked_ambiguity"
    BLOCKED_UNCLASSIFIED = "blocked_unclassified"
    ACCEPTED_RED = "accepted_red"


class PacketKind(str, Enum):
    FRESH = "fresh"
    REPAIR = "repair"


class DependencyDisposition(str, Enum):
    ALREADY_PLANNED = "already_planned"
    ADD_PREREQUISITE = "add_prerequisite"
    REJECT_DEPENDENCY = "reject_dependency"


class RetryRoute(str, Enum):
    TESTER_REPAIR = "tester_repair"
    DEVELOPER_REPAIR = "developer_repair"
    ENVIRONMENT_RECOVERY = "environment_recovery"
