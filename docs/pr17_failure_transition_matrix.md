# PR17 Failure-Transition Matrix Audit

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Protected legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Audit method

- Re-audited the live coordinator, failure router, dependency planner, review progression, persistence records, and focused tests at branch `HEAD` before this closure update.
- Baseline focused suite before the final closure edits was green on the live branch for:
  - `tests/development/test_failure_progression.py`
  - `tests/development/test_behavior_contract_coordinator.py`
  - `tests/execution/test_rack_ai_cli_gateway.py`
- Post-alignment focused proof on the closure changes:
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py tests/execution/test_rack_ai_cli_gateway.py`
  - Result: `123 passed, 11456 warnings in 1.66s`

## State authority

- `current_pool` is the authoritative executable runtime state.
- `contract.status` is the durable high-level contract lifecycle summary.
- `failure_progress.state` is durable sideband evidence about the most recent failure route, not an independent dispatcher.
- Resume behavior is keyed by persisted `current_pool`; `failure_progress.state` preserves audit evidence, route metadata, retry history, and repair packets.

## Final active mechanical failure taxonomy

Every active route below is implemented end to end and has status `A`.

| Classification | Producer | Action | Runtime route | Authoritative pool | Resume semantics | Tests | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `executor_infrastructure_failure` | `FailureObservationBuilder` on executor `transport_error` | `block_executor` | Preserve failure evidence, do not promote candidate, stop in executor-blocked terminal state | `blocked_executor` | Terminal on resume; no retry budget consumed | `test_executor_failure_stops_safely_in_blocked_executor_pool`, `test_resume_blocked_executor_is_terminal_and_does_not_execute` | `A` |
| `environment_failure` | `FailureObservationBuilder` on missing runtime or unavailable toolchain evidence | `recover_environment` | One bounded ATHBA environment recovery attempt; success reruns same phase from same trusted base, failure blocks environment | `cycle_active` on recovery retry, `blocked_environment` on failed recovery | Resume preserves the prior recovery count and either reruns the same phase or remains terminally blocked | `test_environment_recovery_success_reruns_from_trusted_revision`, `test_environment_recovery_exhaustion_blocks_environment_truthfully`, `test_resume_environment_recovery_success_reruns_without_resetting_count`, `test_resume_blocked_environment_is_terminal_and_does_not_execute` | `A` |
| `resource_limit_failure` | `FailureObservationBuilder` on timeout, OOM, or storage exhaustion evidence | `split_packet` | Split into bounded child work or fail closed to replan when unsafe | `tdd_ready` for executable children, `replan_ready` when split is unsafe | Resume continues from persisted split lineage and trusted-base rules | `test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision`, `test_resume_split_uses_persisted_children_without_replanning`, `test_cannot_split_resource_limit_failure_replans_without_child_work`, `test_split_depth_exhaustion_replans_without_calling_split_planner` | `A` |
| `syntax_or_parse_failure` | `FailureObservationBuilder` on syntax/parse evidence | `assess_mechanical_dependency` | Dependency planner chooses `already_planned`, `add_prerequisite`, or phase-correct role repair | `tdd_ready` for dependency deferral, `cycle_active` for bounded repair | Resume follows persisted dependency decisions or repair packets from the same trusted base | `test_syntax_failure_already_planned_dependency_defers_and_parent_resumes_after_resume`, `test_syntax_failure_add_prerequisite_synthesizes_requirement_and_parent_resumes_after_resume`, `test_syntax_failure_reject_dependency_routes_to_tester_repair_from_semantic_base` | `A` |
| `build_or_link_failure` | `FailureObservationBuilder` on build/link/package evidence | `assess_mechanical_dependency` | Same dependency-planner route as syntax/parse; GREEN reject-dependency repairs stay with Developer | `tdd_ready` or `cycle_active` depending on planner disposition | Resume preserves dependency decision or Developer repair route from accepted RED base | `test_build_link_failure_reject_dependency_routes_to_developer_repair_from_red_base` | `A` |
| `test_collection_or_bootstrap_failure` | `FailureObservationBuilder` on collection/bootstrap/import evidence | `assess_mechanical_dependency` | Same dependency-planner route as syntax/parse | `tdd_ready` for deferral, `cycle_active` for repair | Resume follows the persisted dependency or repair state without promoting the failed candidate | `test_collection_bootstrap_failure_uses_dependency_deferral_route` | `A` |
| `security_or_execution_policy_violation` | `FailureObservationBuilder` on Rack AI policy evidence | `repair_candidate` | Phase-aware policy/scope resolver chooses RED Tester repair, GREEN Developer repair, or fail-closed ATHBA defect route | `cycle_active` for candidate repair, `replan_ready` for ATHBA defect | Resume preserves originating phase, owner, paths, and trusted base | `test_red_security_violation_routes_to_tester_repair`, `test_green_security_violation_routes_to_developer_repair`, `test_resume_green_security_violation_retry_preserves_developer_route_and_red_base`, `test_athba_request_defect_policy_violation_fails_closed_without_role_blame` | `A` |
| `change_scope_violation` | `FailureObservationBuilder` on changed-path or allowed-path evidence | `repair_candidate` | Phase-aware policy/scope resolver chooses RED Tester repair, GREEN Developer repair, or explicit replanning | `cycle_active` for candidate repair, `replan_ready` for scope-change or ATHBA defect | Resume preserves exact changed and allowed paths plus the originating role route | `test_red_change_scope_violation_routes_to_tester_repair`, `test_green_change_scope_violation_routes_to_developer_repair`, `test_resume_red_change_scope_violation_retry_preserves_tester_route_and_base`, `test_change_scope_within_contract_phase_scope_replans_without_role_blame` | `A` |
| `tester_candidate_defect` | Generic RED failed-candidate fallback | `repair_tester` | Bounded Tester repair from semantic trusted base | `cycle_active`, then `replan_ready` on budget exhaustion | Resume preserves Tester repair packet and retry counts | `test_green_cannot_begin_before_accepted_red_and_tester_failures_use_bounded_retries`, `test_resume_tester_repair_retry_preserves_transition_and_trusted_base` | `A` |
| `developer_candidate_defect` | Generic GREEN failed-candidate fallback | `repair_developer` | Bounded Developer repair from accepted RED trusted base | `cycle_active`, then `replan_ready` on budget exhaustion | Resume preserves Developer repair packet and retry counts | `test_green_generic_candidate_failure_routes_as_developer_candidate_defect_and_recovers`, `test_resume_developer_repair_retry_preserves_transition_and_red_base` | `A` |

## Compatibility-only vocabulary

These values still decode for persisted snapshots, but they are no longer claimed as active independent PR17 runtime routes.

| Classification | Why it is not an active independent route | Compatibility treatment |
| --- | --- | --- |
| `dependency_or_prerequisite_failure` | No live producer exists. Real dependency handling is reached through syntax/build/bootstrap classifications plus persisted dependency decisions. | Remains decodable from persisted payloads; documented as legacy folded into dependency assessment. |
| `contract_or_requirement_ambiguity` | No deterministic ambiguity producer exists in live PR17 control flow. | Remains decodable; not claimed as active production vocabulary. |
| `expected_behavior_red` | Accepted RED is normal TDD success state, not a failure. | Remains decodable; documented as legacy vocabulary replaced by normal cycle state. |
| `accumulated_regression` | No trustworthy producer distinguishes accumulated regression from other candidate defects in current mechanics. | Remains decodable; folded into candidate-defect routing until a real producer exists. |
| `semantic_integration_failure` | Review `replan_required` is a semantic review verdict, not a mechanical failure classification route. | Remains decodable; semantic review is documented separately. |
| `review_quality_failure` | Review `repair_required` is a semantic review verdict with its own bounded repair loop, not a mechanical failure route. | Remains decodable; semantic review is documented separately. |
| `architecture_constraint_violation` | No live deterministic architecture validator produces it. | Remains decodable; not claimed as active PR17 vocabulary. |
| `unclassified_failure` | Active failed-candidate routing always falls back to phase-correct candidate defect instead. | Remains decodable; no separate production analysis loop is claimed. |

## Semantic review verdicts

Semantic review is represented outside the mechanical failure taxonomy.

| Review verdict | Runtime route | Pool | Persistence |
| --- | --- | --- | --- |
| `approved` | Continue through normal completion or next work selection | `approved` then normal progression | Stored in cycle review result |
| `repair_required` | Bounded semantic repair loop without entering failure progression | `repair_ready` | Stored in cycle review result and semantic repair count |
| `replan_required` | Fail closed to replanning without mechanical failure classification | `replan_ready` | Stored in cycle review result and contract blocker |

## Conclusion

- No active PR17 row remains `B`, `C`, `D`, or `E`.
- Every active mechanical failure classification has a real producer, executable route, persistence story, and resume proof.
- Deprecated vocabulary is retained only for backward-compatible decoding and is no longer presented as active runtime behavior.
