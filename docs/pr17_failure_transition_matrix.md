# PR17 Failure-Transition Matrix Audit

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Protected legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Audit method

This audit was completed by direct source and test inspection before any behavior changes.

Primary runtime surfaces inspected:

- `core/development/behavior_contract_coordinator.py`
- `core/development/failure_values.py`
- `core/development/failure_records.py`
- `core/development/failure_state.py`
- `core/development/failure_transitions.py`
- `core/development/failure_policy.py`
- `core/development/contract_run_domain.py`
- `core/datastore/repos/tdd_state_repo.py`
- `scripts/run_pr17_independent_reservation_book.py`
- `core/development/specification_reconciliation.py`

Focused baseline executed on 2026-08-31:

- `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py`
- Result: `72 passed, 6629 warnings in 1.12s`

Status legend:

- `A` = fully implemented end-to-end
- `B` = partially implemented
- `C` = policy / type representation only
- `D` = missing
- `E` = implemented incorrectly

## Key architectural finding

Failure classification and durable `failure_progress.state` exist, but the active coordinator does **not** dispatch on `FailureRouteState`.

`BehaviorContractCoordinator.run_contract()` stops only when `current_pool` is `completed` or `replan_ready`, and `_advance()` dispatches only on:

- `tdd_ready`
- `approved`
- `cycle_active`
- `review_ready`
- `repair_ready`

As a result, most failure-route states are persisted as sideband evidence, while the real runtime state machine resumes from `current_pool` instead.

## Primary matrix

| # | Classification | Action | Observation Produced? | Runtime Route | Phase Correct? | Retry/Persistence | Resume | Tests | Status | Required Work |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `executor_infrastructure_failure` | `block_executor` | Yes. `FailureObservationBuilder` adds it when executor status is `transport_error`. | `FailedCandidateRouter.route()` falls through to `_route_state_for_failure()` and records `failure_progress.state=blocked_executor`, but sets `current_pool=replan_ready`. | Broadly yes, phase-agnostic. | Decision, packet, history persist. No dedicated executor recovery route. | Resume stops at `replan_ready`; nothing consumes `blocked_executor` directly. | `test_every_documented_class_has_fixed_priority_and_action`, `test_progress_state_round_trips_decision_retry_lineage_and_blocker` | `B` | Add a real blocked-executor route or make the authoritative dispatcher/state vocabulary consistent. |
| 2 | `environment_failure` | `recover_environment` | Yes. Builder matches text fragments such as `runtime executable`, `pytest is unavailable`, or `environment`. | Special branch in `FailedCandidateRouter.route()` attempts `_environment_recovery_succeeded()`. Success reruns from trusted revision; failure falls through to `awaiting_environment_recovery` plus `current_pool=replan_ready`. | Broadly yes, phase-agnostic. | Retry budget exists and is persisted through `RetryRoute.ENVIRONMENT_RECOVERY`, but it is hard-coded to one attempt. | Resume does not re-enter a dedicated environment-recovery state; it returns from `replan_ready`. | Policy tests only; no focused route test proving success and failure branches. | `B` | Add direct route coverage and align persisted route state with resumable coordinator behavior. |
| 3 | `resource_limit_failure` | `split_packet` | Yes. Builder matches `timeout`, `out of memory`, `no space left`, or `resource exhausted`. | No executable split route exists. Fallback records `failure_progress.state=awaiting_split` and exits with `current_pool=replan_ready`. | No phase-specific behavior. | Split-related state types exist, but no production branch populates `splits` or `split_children`. | No split consumer or resume path exists. | Policy coverage only. | `B` | Implement or explicitly defer real packet splitting; today the route is classification plus persisted label only. |
| 4 | `syntax_or_parse_failure` | `assess_mechanical_dependency` | Yes. Builder matches `SyntaxError`, `parse error`, or `invalid syntax`. | `FailedCandidateRouter.route()` sends it to `DependencyPrerequisitePlanner.decide()`. `already_planned` or `add_prerequisite` defer work; `reject_dependency` falls into bounded role repair. | Broadly yes. Repair role follows phase, dependency assessment is phase-neutral. | Deferral, dependency decisions, retry counts, packets, and run state persist. | Resume works indirectly through `current_pool=tdd_ready` or `cycle_active`, not through `FailureRouteState`. | `test_rejected_red_is_persisted_and_cannot_become_green_base`, `test_dependency_prerequisite_planner_sends_reasoning_request_boundary` | `B` | Add direct proof for all three planner dispositions and make the dependency route semantics explicit in the matrix runner/tests. |
| 5 | `build_or_link_failure` | `assess_mechanical_dependency` | Yes. Builder matches `build failed`, `linker`, `link failure`, or `packaging failed`. | Same branch as syntax/parse. | Broadly yes. | Same persistence as row 4. | Same as row 4. | Policy coverage only; no direct build/link route test. | `B` | Add route-specific tests; current implementation is shared heuristic plumbing, not directly proven. |
| 6 | `test_collection_or_bootstrap_failure` | `assess_mechanical_dependency` | Yes. Builder matches `error collecting`, `ImportError`, `ModuleNotFoundError`, or `bootstrap`. | Same dependency-planner branch as rows 4 and 5. If planner rejects dependency and repair budget is exhausted, lane exits to `replan_ready`. | Broadly yes. | Deferral path and repair path both persist correctly. | Resume uses persisted `current_pool`; failed RED never becomes GREEN base. | `test_rejected_red_is_persisted_and_cannot_become_green_base`, failure policy unit tests | `B` | Add positive coverage for prerequisite deferral and post-resume continuation from persisted dependency state. |
| 7 | `security_or_execution_policy_violation` | `repair_tester` | Yes. Builder matches `path_policy`, `policy`, or `unauthorized`. | No dedicated policy route branch. It falls into generic repair logic. Actual packet role and retry route are chosen from phase, not from `decision.action`. GREEN therefore becomes Developer repair despite action=`repair_tester`. | RED route is plausible. GREEN route is runtime-phase-based rather than policy-based. | Retry and packets persist, but the persisted action and executed route can disagree. | Resume follows `cycle_active` / `replan_ready`; failure-route state is only metadata. | Only classification/action table coverage. No phase-ownership regression test. | `E` | Align policy mapping, runtime route, and tests. Today the action table and executed route disagree. |
| 8 | `change_scope_violation` | `repair_tester` | Yes. Builder matches `changed_paths`, `allowed_paths`, or `out-of-scope`. | Same generic repair path as row 7. GREEN again routes to Developer repair despite policy action `repair_tester`. | Same mismatch as row 7. | Same persistence mismatch as row 7. | Same as row 7. | Policy coverage only. No direct route test. | `E` | Same as row 7: either change the policy mapping or make runtime explicitly honor the policy. |
| 9 | `dependency_or_prerequisite_failure` | `replan_dependency` | No production producer found. It appears in enums, policy tables, and unit tests only. | No runtime branch selects this classification from live evidence. Dependency behavior is reached through rows 4 to 6 instead. | N/A. | `FailureProgressState.defer_for_prerequisites()` persists dependency state, but under other dominant classifications. | No resume path keyed by this classification. | `test_prerequisite_deferral_preserves_state_and_records_declared_dependency` | `C` | Add a real producer and route if this classification should exist as a first-class decision; otherwise remove or fold it into documented behavior. |
| 10 | `contract_or_requirement_ambiguity` | `block_ambiguity` | No production producer found. | `_route_state_for_failure()` knows how to map it to `blocked_ambiguity`, but no live code emits it. | N/A. | Persistable if manually injected; not produced in real routing. | No real resume path. | Policy coverage only. | `C` | Add an actual ambiguity detector and blocking path, or document it as not yet implemented. |
| 11 | `tester_candidate_defect` | `repair_tester` | Yes. This is the RED fallback when no more specific class is detected. | Generic repair branch creates a Tester repair packet, increments `tester_repair`, retries from semantic base, then exits to `replan_ready` on budget exhaustion. | Yes for RED; it is RED-only by construction. | Retry budget, packet, history, and final block reason persist. | Resume works from persisted snapshot because `current_pool` remains `cycle_active` during retry and `replan_ready` on exhaustion. | `test_green_cannot_begin_before_accepted_red_and_tester_failures_use_bounded_retries`, failure policy retry tests | `A` | Keep as authoritative baseline for the bounded RED repair route. |
| 12 | `developer_candidate_defect` | `repair_developer` | Yes. This is the GREEN fallback when no more specific class is detected. | Generic repair branch creates a Developer repair packet, increments `developer_repair`, retries from accepted RED base, then exits to `replan_ready` on exhaustion. | Broadly yes for GREEN. | Retry budget, packet, history, and final block reason persist. | Resume behavior follows persisted `current_pool`. | Shared router/unit coverage exists, but no direct developer-defect route test names this classification explicitly. | `B` | Add a focused GREEN defect regression that proves developer repair and trusted-base preservation under this exact classification. |
| 13 | `expected_behavior_red` | `accept_red` | No. The classification is never emitted by `FailureObservationBuilder`. | Expected RED is handled outside `FailureProgressionPolicy`: accepted RED proceeds on the normal success path, and `already_satisfied` is handled by `_is_red_already_satisfied_from_phase()`. `FailureRouteState.ACCEPTED_RED` is never consumed. | N/A in policy terms. | Accepted RED revisions do persist in cycle state, but not as this classification or route state. | Resume uses accepted RED in `cycle.red_phase.accepted_revision`, not `accepted_red` route state. | Legacy/TDD accepted-RED behavior tests exist; no policy-route test for this classification. | `C` | Either introduce a true `expected_behavior_red` classification path or document that accepted RED is represented by the phase-success path instead. |
| 14 | `accumulated_regression` | `repair_regression` | No production producer found. | No dedicated accumulated-regression route exists. The generic repair branch would honor the action if a classification were injected, but no classifier produces it. | N/A. | No production evidence that focused-vs-accumulated failure is distinguished. | No dedicated resume path. | Policy coverage only. | `C` | Add a real accumulated-regression detector and route, or remove it from the claimed exhaustive implementation. |
| 15 | `semantic_integration_failure` | `replan_integration` | No production producer found. | Review-stage `replan_required` exists in `ReviewReadyProgressor`, but it bypasses `FailureProgressionPolicy` and does not persist this classification in `failure_progress`. | Review-phase semantics exist, but not through the claimed classification path. | Review outcome and pool persist, but no dominant classification, action, or failure history entry is recorded for this class. | Resume from `replan_ready` works, but not as an integration-classified route. | Review replan tests exist (`test_replan_required_moves_to_replan_ready_and_stops_lane`), but none prove this classification. | `E` | Align review-stage replan behavior with the declared classification/policy model, or narrow the claim. |
| 16 | `review_quality_failure` | `repair_review` | No production producer found. | Review-stage `repair_required` exists in `ReviewReadyProgressor`, but it also bypasses `FailureProgressionPolicy` and `failure_progress`. | Review-phase behavior is conceptually correct, but classification/policy wiring is absent. | Semantic repair budget persists in cycle state, not in failure progression state. | Resume from `repair_ready` works through `current_pool`, not through a classified failure route. | `test_repair_required_moves_to_repair_ready`, `test_repair_result_returns_to_review_ready_before_final_approval`, `test_repair_attempts_are_bounded` | `E` | Either classify review failures explicitly or stop representing them as implemented in the failure-classification matrix. |
| 17 | `architecture_constraint_violation` | `block_architecture` | No production producer found. | `_route_state_for_failure()` maps it to `blocked_architecture`, but no live producer or runtime branch emits it. | N/A. | Persistable only if manually supplied. | No dedicated resume behavior. | Policy coverage only. | `C` | Add a real architecture validator feeding failure progression, or document the route as not implemented. |
| 18 | `unclassified_failure` | `analyze_unclassified` | Not from active failed-candidate routing. `FailureDecisionPolicy` chooses it only when observations have no plausible classes, but `FailureObservationBuilder` always inserts a Tester or Developer fallback instead. | No production branch builds `UnclassifiedAnalysis` or blocks on a real unclassified route. | N/A. | `UnclassifiedAnalysis` is typed and persistable, but never created in production. | No live resume path. | `test_empty_plausible_evidence_fails_closed_as_unclassified`, typed-state persistence tests | `C` | Add a real bounded unclassified-analysis route or remove the claim that it is currently implemented. |

## State-machine audit

### Contract run pools

| State | Writer(s) | Reader(s) | Reachable? | Resumable? | Notes |
| --- | --- | --- | --- | --- | --- |
| `tdd_ready` | initial run-state creation; dependency deferral; targeted gap selection; targeted gap reinsertion; RED already satisfied path | `BehaviorContractCoordinator._advance()` -> `ReadyPoolProgressor.advance()` | Yes | Yes | Real dispatcher state. |
| `cycle_active` | ready-pool step selection; environment-recovery rerun; generic repair retry path | dispatcher -> `CycleActiveProgressor.advance()` | Yes | Yes | Real dispatcher state for RED/GREEN execution. |
| `review_ready` | accepted GREEN; successful review repair | dispatcher -> `ReviewReadyProgressor.advance()` | Yes | Yes | Real dispatcher state. |
| `repair_ready` | review verdict `repair_required` under budget | dispatcher -> `RepairReadyProgressor.advance()` | Yes | Yes | Real dispatcher state. |
| `approved` | review approval; checklist-targeted approval without checklist completion | dispatcher treats it like `tdd_ready` via `ReadyPoolProgressor.advance()` | Yes | Yes | Transitional real state. |
| `replan_ready` | failed route exits; review replan; semantic repair exhaustion; untraceable specification gap | `run_contract()` terminal return | Yes | No automatic resume path | Terminal stop state today. |
| `completed` | `_completed_run_state()`; review approval after full checklist proof | `run_contract()` terminal return | Yes | Terminal | Final success state. |

### Failure route states

| Failure route state | Writer(s) | Reader(s) | Reachable? | Resumable? | Notes |
| --- | --- | --- | --- | --- | --- |
| `active` | default state; environment recovery success | persistence only | Yes | Sideband only | Not a coordinator dispatcher state. |
| `awaiting_repair` | generic repair record path | persistence and retry counting only | Yes | Indirect only | `current_pool` remains `cycle_active`. |
| `deferred_dependency` | `FailureStateTransitions.defer_for_prerequisites()` | only indirect data readers such as prerequisite lineage checks | Yes | Indirect only | Actual resumption occurs from `current_pool=tdd_ready`. |
| `awaiting_prerequisite` | none found | none found | No | No | Dead vocabulary. |
| `awaiting_environment_recovery` | `_route_state_for_failure(environment_failure)` on failed recovery path | none found | Yes | No dedicated resume | Written, not dispatched. |
| `awaiting_split` | `_route_state_for_failure(resource_limit_failure)` | none found | Yes | No | Written, not dispatched. |
| `blocked_executor` | `_route_state_for_failure(executor_infrastructure_failure)` | none found | Yes | No | Written, not dispatched. |
| `blocked_architecture` | `_route_state_for_failure(architecture_constraint_violation)` | none found | Only if manually classified | No | No live producer. |
| `blocked_ambiguity` | `_route_state_for_failure(contract_or_requirement_ambiguity)` | none found | Only if manually classified | No | No live producer. |
| `blocked_unclassified` | `_route_state_for_failure(unclassified_failure)` | none found | Only if manually classified | No | No live producer/analysis builder. |
| `accepted_red` | none found | none found | No | No | Dead vocabulary; accepted RED is represented elsewhere. |

## Transition consistency findings

- `FailureProgressionPolicy` is authoritative only for dominant classification, action lookup, retry counting, and failure-state recording. It is **not** the active runtime dispatcher.
- `current_pool` and `contract.status` are the real progression states. `failure_progress.state` is usually descriptive metadata.
- `security_or_execution_policy_violation` and `change_scope_violation` are mapped to `repair_tester`, but executed repair ownership is chosen from phase. This creates a policy/action versus runtime-route mismatch.
- `dependency_or_prerequisite_failure`, `contract_or_requirement_ambiguity`, `accumulated_regression`, `architecture_constraint_violation`, and `unclassified_failure` currently exist as enum/policy vocabulary without a live production producer.
- `semantic_integration_failure` and `review_quality_failure` are represented functionally by review verdicts, but those verdict routes bypass failure classification, failure history, and failure-policy action recording.
- `resource_limit_failure -> split_packet` has no split planner, no child scheduling branch, no split persistence writer in production, and no resume consumer.
- `expected_behavior_red -> accept_red` is not an active failure route. Accepted RED is represented by the normal accepted RED phase path, while `FailureRouteState.ACCEPTED_RED` is dead.
- `awaiting_prerequisite` and `accepted_red` are dead vocabulary today.
- `blocked_*` failure states are written, but coordinator termination/resume still hinges on `current_pool=replan_ready` rather than those states.

## Evidence-backed conclusions

- The repository **does** implement a real bounded RED repair route for `tester_candidate_defect`.
- The repository **does** implement real GREEN review and semantic repair progression, but not through the claimed failure-classification matrix for `review_quality_failure` or `semantic_integration_failure`.
- The repository **partially** implements the mechanical dependency-assessment family driven by syntax/build/bootstrap failures.
- The repository **does not** implement the claimed packet-splitting, ambiguity-blocking, architecture-blocking, accumulated-regression, or bounded unclassified-analysis routes as live production behavior.
- The repository currently presents a broader failure taxonomy than the executable state machine actually supports.

## Residual findings

- This audit did not change runtime behavior.
- No Rack AI source or configuration was modified.
- The next corrective step should be a source-of-truth decision: either narrow the declared PR17 matrix to what is executable, or implement the missing producers and route consumers so the matrix is truthful.
