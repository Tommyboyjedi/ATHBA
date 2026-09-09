# PR17 Failure State-Machine Closure Ledger

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Protected legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Final active PR17 failure taxonomy

- `executor_infrastructure_failure`
- `environment_failure`
- `resource_limit_failure`
- `syntax_or_parse_failure`
- `build_or_link_failure`
- `test_collection_or_bootstrap_failure`
- `security_or_execution_policy_violation`
- `change_scope_violation`
- `tester_candidate_defect`
- `developer_candidate_defect`

## Original classification audit

| Original classification | Original action | Active after this session? | Real producer | Real runtime route | Authoritative runtime pool | Persistence | Resume semantics | Tests | Rationale / compatibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `executor_infrastructure_failure` | `block_executor` | YES | `FailureObservationBuilder` on executor `transport_error` | Fail closed without candidate promotion or role repair | `blocked_executor` | Failure history and blocker persist in `failure_progress`; trusted base unchanged | Terminal on resume; no retry budget consumed | `test_executor_failure_stops_safely_in_blocked_executor_pool`, `test_resume_blocked_executor_is_terminal_and_does_not_execute` | Active route kept. Docs now describe `blocked_executor` as the real terminal pool. |
| `environment_failure` | `recover_environment` | YES | `FailureObservationBuilder` on unavailable runtime/toolchain evidence | One bounded environment recovery attempt; success reruns same phase, failure blocks environment | `cycle_active` on retry, `blocked_environment` on failure | Recovery count, failure history, blocker, and trusted base persist | Resume preserves recovery count and route | `test_environment_recovery_success_reruns_from_trusted_revision`, `test_environment_recovery_exhaustion_blocks_environment_truthfully`, `test_resume_environment_recovery_success_reruns_without_resetting_count`, `test_resume_blocked_environment_is_terminal_and_does_not_execute` | Active route kept. |
| `resource_limit_failure` | `split_packet` | YES | `FailureObservationBuilder` on timeout/OOM/storage exhaustion evidence | Bounded packet split or fail-closed replanning | `tdd_ready` for child execution, `replan_ready` when split is unsafe | Split lineage, child ordering, trusted-base rules, and blockers persist | Resume continues from persisted split lineage | `test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision`, `test_resume_split_uses_persisted_children_without_replanning`, `test_cannot_split_resource_limit_failure_replans_without_child_work`, `test_split_depth_exhaustion_replans_without_calling_split_planner` | Active route kept. |
| `syntax_or_parse_failure` | `assess_mechanical_dependency` | YES | `FailureObservationBuilder` on syntax/parse evidence | Dependency decision or phase-correct role repair | `tdd_ready` or `cycle_active` | Dependency decisions, repair packets, and retry lineage persist | Resume follows persisted dependency or repair route | `test_syntax_failure_already_planned_dependency_defers_and_parent_resumes_after_resume`, `test_syntax_failure_add_prerequisite_synthesizes_requirement_and_parent_resumes_after_resume`, `test_syntax_failure_reject_dependency_routes_to_tester_repair_from_semantic_base` | Active route kept. |
| `build_or_link_failure` | `assess_mechanical_dependency` | YES | `FailureObservationBuilder` on build/link/package evidence | Shared dependency assessment or phase-correct repair | `tdd_ready` or `cycle_active` | Same persisted dependency/repair state as syntax route | Resume keeps dependency or Developer repair ownership | `test_build_link_failure_reject_dependency_routes_to_developer_repair_from_red_base` | Active route kept; folded into the shared dependency-assessment implementation. |
| `test_collection_or_bootstrap_failure` | `assess_mechanical_dependency` | YES | `FailureObservationBuilder` on collection/bootstrap/import evidence | Shared dependency assessment or phase-correct repair | `tdd_ready` or `cycle_active` | Same persisted dependency/repair state as syntax route | Resume keeps persisted dependency or repair route | `test_collection_bootstrap_failure_uses_dependency_deferral_route` | Active route kept; folded into the shared dependency-assessment implementation. |
| `security_or_execution_policy_violation` | `repair_candidate` | YES | `FailureObservationBuilder` on Rack AI policy evidence | Phase-aware candidate repair or fail-closed ATHBA defect replan | `cycle_active` or `replan_ready` | Policy evidence, originating phase, owner, and trusted base persist | Resume preserves owner and route | `test_red_security_violation_routes_to_tester_repair`, `test_green_security_violation_routes_to_developer_repair`, `test_resume_green_security_violation_retry_preserves_developer_route_and_red_base`, `test_athba_request_defect_policy_violation_fails_closed_without_role_blame` | Active route kept. |
| `change_scope_violation` | `repair_candidate` | YES | `FailureObservationBuilder` on changed-path/allowed-path evidence | Phase-aware candidate repair or explicit replanning | `cycle_active` or `replan_ready` | Changed paths, allowed paths, owner, and trusted base persist | Resume preserves exact path evidence and owner | `test_red_change_scope_violation_routes_to_tester_repair`, `test_green_change_scope_violation_routes_to_developer_repair`, `test_resume_red_change_scope_violation_retry_preserves_tester_route_and_base`, `test_change_scope_within_contract_phase_scope_replans_without_role_blame` | Active route kept. |
| `dependency_or_prerequisite_failure` | `replan_dependency` | NO | No live producer | Folded into syntax/build/bootstrap dependency decisions | N/A | Still decodes in persisted payloads | No independent resume branch | `test_legacy_failure_classifications_remain_decodable_from_persisted_payloads` | Compatibility-only legacy vocabulary. |
| `contract_or_requirement_ambiguity` | `block_ambiguity` | NO | No deterministic live producer | Removed from active PR17 runtime taxonomy | N/A | Still decodes in persisted payloads | No independent resume branch | `test_legacy_failure_classifications_remain_decodable_from_persisted_payloads` | Compatibility-only legacy vocabulary. |
| `tester_candidate_defect` | `repair_tester` | YES | Generic RED fallback | Bounded Tester repair from semantic base | `cycle_active`, then `replan_ready` on exhaustion | Retry count, packet, and failure history persist | Resume keeps Tester repair route | `test_green_cannot_begin_before_accepted_red_and_tester_failures_use_bounded_retries`, `test_resume_tester_repair_retry_preserves_transition_and_trusted_base` | Active route kept. |
| `developer_candidate_defect` | `repair_developer` | YES | Generic GREEN fallback | Bounded Developer repair from accepted RED base | `cycle_active`, then `replan_ready` on exhaustion | Retry count, packet, and failure history persist | Resume keeps Developer repair route | `test_green_generic_candidate_failure_routes_as_developer_candidate_defect_and_recovers`, `test_resume_developer_repair_retry_preserves_transition_and_red_base` | Active route kept. |
| `expected_behavior_red` | `accept_red` | NO | No live producer because accepted RED is success, not failure | Folded into normal TDD phase success | `approved` / normal cycle state | Accepted RED persists in cycle state, not as failure progression | Resume uses cycle RED acceptance state | `test_legacy_failure_classifications_remain_decodable_from_persisted_payloads` | Compatibility-only legacy vocabulary. |
| `accumulated_regression` | `repair_regression` | NO | No trustworthy live producer | Folded into candidate-defect routing until a real detector exists | N/A | Still decodes in persisted payloads | No independent resume branch | `test_legacy_failure_classifications_remain_decodable_from_persisted_payloads` | Compatibility-only legacy vocabulary. |
| `semantic_integration_failure` | `replan_integration` | NO | No mechanical producer; this is a semantic review verdict concept | Removed from mechanical taxonomy; represented by review `replan_required` | `replan_ready` | Review result persists in cycle state | Resume obeys `current_pool` and cycle review result | `test_semantic_replan_uses_review_result_and_replan_pool`, `test_replan_required_moves_to_replan_ready_and_stops_lane` | Compatibility-only legacy vocabulary. |
| `review_quality_failure` | `repair_review` | NO | No mechanical producer; this is a semantic review verdict concept | Removed from mechanical taxonomy; represented by review `repair_required` | `repair_ready` | Review result and semantic repair count persist in cycle state | Resume obeys `current_pool` and cycle review result | `test_review_repair_uses_review_state_and_preserves_runtime_flow`, `test_repair_attempts_are_bounded` | Compatibility-only legacy vocabulary. |
| `architecture_constraint_violation` | `block_architecture` | NO | No live deterministic producer | Removed from active PR17 taxonomy | N/A | Still decodes in persisted payloads | No independent resume branch | `test_legacy_failure_classifications_remain_decodable_from_persisted_payloads` | Compatibility-only legacy vocabulary. |
| `unclassified_failure` | `analyze_unclassified` | NO | No active producer because failed-candidate routing always falls back to phase-correct candidate defect | Removed from active PR17 taxonomy | N/A | Still decodes in persisted payloads | No independent resume branch | `test_legacy_failure_classifications_remain_decodable_from_persisted_payloads` | Compatibility-only legacy vocabulary. |

## Semantic review boundary

Semantic review remains a separate bounded state machine.

- `approved` advances through the normal success path.
- `repair_required` enters `repair_ready` with persisted cycle review state and bounded semantic repair count.
- `replan_required` stops in `replan_ready` with persisted cycle review state.
- No synthetic mechanical failure classification is written for those review verdicts.

## State authority

- `current_pool` is the authoritative runtime dispatcher.
- `contract.status` is the durable lifecycle summary.
- `failure_progress.state` is durable failure-sideband evidence for audit, retry lineage, dependency decisions, split lineage, and repair packets.

## Focused proof

- Focused closure suite:
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py tests/execution/test_rack_ai_cli_gateway.py`
  - Result: `123 passed, 11456 warnings in 1.66s`

## Validation

- Coding gate:
  - `./.venv/bin/python scripts/check_coding_principles.py`
  - Result: `coding principles gate passed`
- Mypy:
  - `./.venv/bin/python -m mypy`
  - Result: `Success: no issues found in 13 source files`
- Full suite:
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q`
  - Result: `276 passed, 29294 warnings in 12.07s`
- Compileall:
  - `./.venv/bin/python -m compileall athba core llm_service tests scripts`
  - Result: passed
- Diff check:
  - `git diff --check`
  - Result: passed
- Legacy verification:
  - `git rev-parse legacy`
  - Result: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Milestone commit SHAs

- `cd55953` `Fix phase-aware policy violation routing`
- `5bb709e` `Document PR17 policy scope routing audit`
- `8c3bdeb` `Align PR17 failure taxonomy with runtime routes`

## Residual findings

- None beyond the explicit compatibility-only legacy vocabulary retained for persisted decode.

INCOMPLETE_ITEMS = NONE
