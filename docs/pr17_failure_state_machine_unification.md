# PR17 Failure State Machine Unification

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Protected legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Checklist

- [x] Confirm original inconsistency
  - Evidence: `BehaviorContractRunState.current_pool` remained the only dispatcher while `FailureProgressState.state` persisted mostly sideband route vocabulary. `BehaviorContractCoordinator.run_contract()` now terminates on `TERMINAL_CONTRACT_POOLS` and candidate/review failure paths flow through one typed transition bridge in `core/development/failure_routing.py`.
  - Tests: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py`
  - Commit SHA: PENDING

- [x] Choose authoritative state architecture
  - Evidence: `current_pool` remains the single orchestration dispatcher. `FailureTransition` now makes the executable consequence of a failure decision explicit: decision, route state, next pool, retry route, blocker, return behavior, packet, and dependency effects.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_pool_state_transitions_persist_in_snapshot_round_trip`
  - Commit SHA: PENDING

- [x] Introduce typed transition object(s)
  - Evidence: Added `FailureTransition`, `CandidateFailureTransitionRequest`, and `ReviewFailureTransitionRequest` in `core/development/failure_routing.py`.
  - Tests: `tests/development/test_failure_progression.py`, `tests/development/test_behavior_contract_coordinator.py::test_review_repair_records_failure_progression_and_preserves_runtime_flow`, `tests/development/test_behavior_contract_coordinator.py::test_semantic_replan_records_failure_progression`
  - Commit SHA: PENDING

- [x] Make failure actions executable rather than decorative
  - Evidence: `behavior_contract_coordinator.py` now routes candidate failures by `ProgressionAction`, not by implicit classification fallthrough. Unsupported actions fail closed to explicit `replan_ready` or truthful blocked states.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_red_security_violation_routes_to_tester_repair`, `tests/development/test_behavior_contract_coordinator.py::test_green_security_violation_routes_to_developer_repair`, `tests/development/test_behavior_contract_coordinator.py::test_red_change_scope_violation_routes_to_tester_repair`, `tests/development/test_behavior_contract_coordinator.py::test_green_change_scope_violation_routes_to_developer_repair`
  - Commit SHA: PENDING

- [x] Correct failure ownership by candidate phase
  - Evidence: `security_or_execution_policy_violation` and `change_scope_violation` now map to `repair_candidate`, with runtime ownership resolved by RED versus GREEN trusted-base semantics instead of a false globally-fixed Tester owner.
  - Tests: same four phase-ownership tests above.
  - Commit SHA: PENDING

- [x] Integrate Senior Review failures into failure progression
  - Evidence: `ReviewReadyProgressor` now uses `_review_failure_transition(...)` plus `failure_routing.apply_review_failure_transition(...)`, preserving review repair budgets while recording dominant classification and action history.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_review_repair_records_failure_progression_and_preserves_runtime_flow`, `tests/development/test_behavior_contract_coordinator.py::test_semantic_replan_records_failure_progression`
  - Commit SHA: PENDING

- [x] Make executor and environment terminal semantics truthful
  - Evidence: Added contract pools `blocked_executor`, `blocked_environment`, and `split_required`. Environment recovery success reruns from trusted revision; exhaustion blocks in `blocked_environment`. Executor transport failures block in `blocked_executor` instead of pretending software replanning can recover rack infrastructure.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_environment_recovery_success_reruns_from_trusted_revision`, `tests/development/test_behavior_contract_coordinator.py::test_environment_recovery_exhaustion_blocks_environment_truthfully`, `tests/development/test_behavior_contract_coordinator.py::test_executor_failure_stops_safely_in_blocked_executor_pool`, `tests/development/test_behavior_contract_coordinator.py::test_resume_blocked_environment_is_terminal_and_does_not_execute`, `tests/development/test_behavior_contract_coordinator.py::test_resume_blocked_executor_is_terminal_and_does_not_execute`
  - Commit SHA: PENDING

- [x] Keep resource splitting explicitly deferred
  - Evidence: `resource_limit_failure` now stops truthfully through `split_required` state vocabulary without implementing split planning or child execution.
  - Tests: focused failure-policy and coordinator persistence coverage; no split execution was added in this phase by design.
  - Commit SHA: PENDING

- [x] Keep expected RED out of active failure routing while preserving compatibility
  - Evidence: Accepted RED remains represented by normal TDD RED success state. Legacy route value compatibility is preserved in enums/deserialization, but new routing does not classify successful RED as failure.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_expected_red_success_path_does_not_create_failure_progression_entry`
  - Commit SHA: PENDING

- [x] Add state consistency invariants
  - Evidence: `validate_failure_progress_state(...)` in `core/development/failure_state.py` now rejects incompatible blocked/terminal combinations and `BehaviorContractRunState.__post_init__` enforces those invariants on persisted state load.
  - Tests: `tests/development/test_failure_progression.py::test_progress_state_round_trips_decision_retry_lineage_and_blocker`, focused coordinator resume tests.
  - Commit SHA: PENDING

- [x] Preserve persistence and resume semantics
  - Evidence: failure history, retry counts, blocker strings, dependency decisions, repair packets, and truthful `current_pool` values persist through `BehaviorContractRunState` and `TddSnapshot` round trips.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_resume_tester_repair_retry_preserves_transition_and_trusted_base`, `tests/development/test_behavior_contract_coordinator.py::test_resume_developer_repair_retry_preserves_transition_and_red_base`, `tests/development/test_behavior_contract_coordinator.py::test_resume_environment_recovery_success_reruns_without_resetting_count`, `tests/development/test_behavior_contract_coordinator.py::test_pool_state_transitions_persist_in_snapshot_round_trip`
  - Commit SHA: PENDING

## Historical compatibility decisions

- Legacy `FailureRouteState` values remain loadable even where new runs no longer generate them actively.
- `expected_behavior_red` remains compatibility vocabulary only; successful RED execution is not reclassified as failure.
- `awaiting_prerequisite` remains historical/dead vocabulary for readability of older saved state; new writes use `deferred_dependency` with explicit prerequisite decisions.
- Review repair and review replan now record failure progression evidence without changing their runtime lanes or semantic repair budget behavior.

## Focused post-refactor evidence

- `87 passed, 8054 warnings in 1.23s`
- Command: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py`

## Residual Phase 2 work

- `resource_limit_failure -> split_packet` remains a truthful deferred stop, not a split planner/executor.
- No new ambiguity-analysis planner was introduced.
- No new architecture validator or unclassified-analysis runner was introduced.
- Dead historical route vocabulary remains loadable for persistence compatibility.

INCOMPLETE_ITEMS = NONE
