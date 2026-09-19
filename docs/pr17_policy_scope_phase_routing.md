# PR17 Policy/Scope Phase Routing Ledger

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Protected legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Before

- `security_or_execution_policy_violation` and `change_scope_violation` both classified correctly, but ATHBA only had a phase-neutral repair fallback after classification.
- The runtime owner happened to come from phase, but the executor boundary discarded `allowed_paths` and `changed_paths`, so ATHBA could not distinguish candidate defect from ATHBA request defect or genuine plan-scope change.
- Persisted failure observations did not record originating phase, work unit identity, or path-policy evidence, so resume had no durable source for a later phase-ownership audit.
- Focused baseline run before edits: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py -q`
- Baseline result: `92 passed, 8521 warnings`

## Semantic Defect

- Classification answered what happened, but not who owned repair.
- ATHBA had no explicit software-development interpretation layer between Rack AI path-policy evidence and the bounded TDD repair routes.
- That made candidate-caused violations, ATHBA request defects, and genuine plan-scope changes look too similar at the coordinator boundary.

## Selected Design

- Preserve the central classification table with `security_or_execution_policy_violation -> repair_candidate` and `change_scope_violation -> repair_candidate`.
- Carry Rack AI `allowed_paths` and `changed_paths` through `WorkUnitExecutionResult.policy_evidence`.
- Persist phase/provenance/path evidence on `FailureObservation` and `RepairPacket`.
- Resolve `repair_candidate` through `PolicyScopeViolationResolver`, which chooses exactly one disposition:
  - role candidate defect
  - ATHBA request defect
  - genuine plan scope change
- Keep the fail-closed outcomes on existing `replan_ready` semantics; do not weaken Rack AI policy and do not fabricate a role repair packet for ATHBA-owned defects.

## Checklist

- [x] Target responsibility: preserve Rack AI path-policy evidence at the ATHBA execution boundary.
  - Implementation evidence: `ExecutionPolicyEvidence` added to `core/execution/work_unit_gateway.py` and mapped from Rack AI packet payload in `core/execution/rack_ai_result.py`.
  - Tests: `tests/execution/test_rack_ai_cli_gateway.py::test_gateway_returns_structured_success_and_uses_argument_array`.
  - Commit SHA: `cd55953`

- [x] Target responsibility: persist phase ownership, work-unit identity, and exact path evidence for candidate failures.
  - Implementation evidence: `FailureObservation` now stores `work_unit_id`, `phase`, `allowed_paths`, and `changed_paths`; `RepairPacket` now stores `originating_phase` and `changed_paths`.
  - Tests: `tests/development/test_failure_progression.py::test_failure_observation_round_trips_policy_scope_evidence`, `tests/development/test_failure_progression.py::test_repair_packet_is_descriptive_and_round_trips`.
  - Commit SHA: `cd55953`

- [x] Target responsibility: route candidate-caused policy violations back to the originating role with bounded retry.
  - Implementation evidence: `core/development/behavior_contract_coordinator.py` resolves `repair_candidate` through `PolicyScopeViolationResolver` and then reuses the existing bounded retry machinery.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_red_security_violation_routes_to_tester_repair`, `tests/development/test_behavior_contract_coordinator.py::test_green_security_violation_routes_to_developer_repair`, `tests/development/test_behavior_contract_coordinator.py::test_red_change_scope_violation_routes_to_tester_repair`, `tests/development/test_behavior_contract_coordinator.py::test_green_change_scope_violation_routes_to_developer_repair`.
  - Commit SHA: `cd55953`

- [x] Target responsibility: fail closed on ATHBA request defects instead of blaming Tester or Developer.
  - Implementation evidence: `PolicyScopeViolationResolver` compares authoritative phase paths with the actual execution contract and returns `athba_request_defect` for inconsistent request/path bindings.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_athba_request_defect_policy_violation_fails_closed_without_role_blame`.
  - Commit SHA: `cd55953`

- [x] Target responsibility: stop for genuine same-phase scope broadening instead of silently broadening allowed paths.
  - Implementation evidence: `PolicyScopeViolationResolver` returns `plan_scope_change` when executor evidence shows same-phase contract paths outside the current work-unit authorization.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_change_scope_within_contract_phase_scope_replans_without_role_blame`.
  - Commit SHA: `cd55953`

- [x] Target responsibility: preserve trusted revision invariants across RED and GREEN retries.
  - Implementation evidence: repair packets retain trusted base, the failed candidate is never promoted, and retries still use the existing per-phase trusted base selection.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_green_security_violation_preserves_developer_retry_budget_and_failed_revision`, `tests/development/test_behavior_contract_coordinator.py::test_red_change_scope_violation_preserves_tester_retry_budget_and_failed_revision`, `tests/development/test_behavior_contract_coordinator.py::test_red_security_violation_retry_can_recover_and_complete`, `tests/development/test_behavior_contract_coordinator.py::test_green_change_scope_violation_retry_can_recover_and_reach_review_normally`.
  - Commit SHA: `cd55953`

- [x] Target responsibility: preserve durable owner selection across restart/resume.
  - Implementation evidence: persisted `FailureObservation` and `RepairPacket` now contain enough phase and path evidence for resumed routing to keep the same owner and trusted base.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_resume_green_security_violation_retry_preserves_developer_route_and_red_base`, `tests/development/test_behavior_contract_coordinator.py::test_resume_red_change_scope_violation_retry_preserves_tester_route_and_base`.
  - Commit SHA: `cd55953`

## RED Route

- RED candidate policy/scope violations keep Tester ownership.
- Retry consumes only `tester_repair`.
- Trusted base remains the run state's semantic base; failed RED is never promoted.

## GREEN Route

- GREEN candidate policy/scope violations keep Developer ownership.
- Retry consumes only `developer_repair`.
- Trusted base remains the accepted RED base for the active cycle; failed GREEN is never promoted.

## ATHBA Orchestration-Defect Route

- If ATHBA constructs an execution contract inconsistent with the authoritative phase path, the route fails closed to `replan_ready`.
- No Tester or Developer repair packet is fabricated.
- Rack AI evidence is preserved in durable failure history for later audit.

## Retry Semantics

- Candidate-owned RED policy/scope violations increment only `RetryRoute.TESTER_REPAIR`.
- Candidate-owned GREEN policy/scope violations increment only `RetryRoute.DEVELOPER_REPAIR`.
- ATHBA request defects and explicit plan-scope changes consume no candidate retry budget.
- Exhaustion still falls through the existing bounded failure route; no extra retry mechanism was added.

## Trusted Revision Semantics

- Rejected candidates are not promoted.
- RED retries continue from the run-state semantic base.
- GREEN retries continue from the accepted RED revision for the active cycle.
- Later corrected candidates still proceed through the normal success path.

## Persistence Compatibility

- Existing persisted state remains readable because new `FailureObservation` and `RepairPacket` fields decode with backward-compatible defaults.
- Persisted action strings remain stable: both classifications still decode through `repair_candidate`.
- Resume uses persisted phase/path evidence instead of re-inferring owner from a tester-only policy string.

## Tests

- Focused post-refactor run: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/execution/test_rack_ai_cli_gateway.py tests/development/test_behavior_contract_coordinator.py`
- Result: `115 passed, 10788 warnings in 1.45s`
- Full suite: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q`
- Result: `268 passed, 28432 warnings in 11.98s`
- Coding gate: `./.venv/bin/python scripts/check_coding_principles.py` -> `coding principles gate passed`
- Mypy: `./.venv/bin/python -m mypy` -> `Success: no issues found in 13 source files`

## Milestone Commit SHAs

- `cd55953` `Fix phase-aware policy violation routing`

## Residual Findings

- `failure_progress.state` remains durable sideband state while `current_pool` remains the real dispatcher; this task did not redesign that broader PR17 runtime contract.
- No Rack AI source or configuration was modified.

INCOMPLETE_ITEMS = NONE
