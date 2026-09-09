# Pre-PR17 Correctness Remediation

- [x] Scope and mandatory inputs reviewed.
  Evidence: Re-read `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the current PR17 description, `docs/pr17-specification-gatekeeper.md`, prior refactor ledgers, and `scripts/check_coding_principles.py` before editing on 2026-08-30.
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Baseline defect audit captured.
  Evidence: Confirmed by direct source inspection before edits:
  - `DependencyPrerequisitePlanner.decide()` built `reasoning_request` but called `self.gateway.reason(request)` with `DependencyDecisionRequest`.
  - `ExecuteTestsBehavior.run()` still called `TestExecutionService.run_tests()` with the stale multi-argument form.
  - `AddToSpecBehavior` and `StartSpecBehavior` referenced undefined `intent`/`agent` names.
  - `AskAQuestionBehavior` and `ChangeSpecBehavior` returned `AgentMessage` on the active Spec path instead of canonical `ChatMessage` lists.
  - `FinalizeSpecBehavior` used the stale compatibility run form and legacy `SpecVersionRepo.find/update` argument shape.
  - `AnalyzeSpecBehavior` still called `SpecVersionRepo.find()` with the old filter/sort/limit positional contract.
  - `BehaviorContractRunState`, `TddSnapshot`, and `CoordinationSnapshot` duplicated `RepositoryBinding` serialization, omitted `environment_resources`, and `CoordinationSnapshot.from_dict()` converted JSON `null` into literal `"None"` strings.
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Dependency prerequisite reasoning boundary repaired.
  Confirmed: YES
  Root cause: wrong object was sent across the reasoning-provider boundary.
  Fix: `core/development/behavior_contract_coordinator.py` now passes the constructed `ReasoningRequest` into `gateway.reason(...)`.
  Regression test: `tests/development/test_behavior_contract_coordinator.py::test_dependency_prerequisite_planner_sends_reasoning_request_boundary`
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Tester execution service boundary repaired.
  Confirmed: YES
  Root cause: active tester behavior was not migrated to the canonical `TestRunRequest` service boundary introduced in Session 6.
  Fix: `core/agents/behaviors/tester/execute_tests_behavior.py` now constructs and passes `TestRunRequest(project_id, test_files, verbose)`.
  Regression test: `tests/behaviors/test_execute_tests_behavior.py::test_execute_tests_behavior_uses_test_run_request_boundary`
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Spec behavior call chain repaired.
  Confirmed: YES
  Root cause: active Spec behaviors had inconsistent execution boundaries, stale repo-call signatures, and non-canonical message return types.
  Fix: `add_to_spec`, `start_spec`, `ask_a_question`, `change_spec`, and `finalize_spec` now execute from `BehaviorExecution`, return `list[ChatMessage] | None`, and use `MongoFindRequest` / `MongoUpdateRequest` on the repo boundary. `AnalyzeSpecBehavior` was also updated to use canonical `MongoFindRequest` after the caller audit found one remaining stale Session 6 repository call.
  Regression tests:
  - `tests/behaviors/test_spec_behavior_boundaries.py::test_spec_behaviors_run_on_active_intents`
  - `tests/behaviors/test_spec_behavior_boundaries.py::test_finalize_spec_behavior_uses_canonical_repo_requests`
  - `tests/integration/test_spec_to_tickets_flow.py::test_spec_finalization_triggers_architect`
  - `tests/integration/test_spec_to_tickets_flow.py::test_full_workflow_spec_to_tickets`
  - `tests/integration/test_spec_to_tickets_flow.py::test_spec_approval_metadata_saved`
  - `tests/behaviors/test_analyze_spec_behavior.py`
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Repository binding persistence repaired.
  Confirmed: YES
  Root cause: `RepositoryBinding` had no owned codec, so three persistence surfaces hand-rolled serialization inconsistently.
  Fix:
  - `core/execution/rack_ai_request.py` now owns `RepositoryBinding.to_dict()` / `RepositoryBinding.from_dict()`.
  - `core/development/contract_run_domain.py` and `core/development/progression.py` now delegate to the shared codec.
  - `environment_resources` now round-trips through `BehaviorContractRunState`, `TddSnapshot`, and `CoordinationSnapshot`.
  - optional binding fields remain `None` instead of becoming the literal string `"None"`.
  Regression tests:
  - `tests/development/test_behavior_contract_coordinator.py::test_behavior_contract_run_state_round_trip_preserves_binding_resources`
  - `tests/development/test_tdd_coordinator.py::test_state_persists_repository_environment_resources`
  - `tests/development/test_coordinator.py::test_coordination_snapshot_preserves_none_binding_fields_and_resources`
  - `tests/execution/test_rack_ai_work_unit_contract.py::test_repository_binding_round_trip_preserves_optional_fields_and_resources`
  - existing compatibility coverage retained in `tests/development/test_project_environment.py::test_legacy_project_state_without_environment_resources_remains_readable`
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Session 6 caller compatibility audit completed.
  Confirmed: YES
  Audited boundaries:
  - `TestExecutionService.run_tests()` callers
  - `SpecVersionRepo.find()` / `update()` callers in active behavior paths
  - `SpecVersionRepo.add_version()` callers
  - behavior execution signatures in active Spec and Tester paths
  - `BehaviorExecution` call sites
  - progression/request-boundary migrations touched by this repair
  Evidence:
  - `ExecuteTestsBehavior` is the active production caller and now uses `TestRunRequest`.
  - `FinalizeSpecBehavior`, `ProjectService`, `SpecService`, and `core/endpoints/spec.py` use canonical request objects.
  - The audit surfaced one additional stale production caller in `AnalyzeSpecBehavior`, which was repaired.
  Residual note: `AnalyzeSpecBehavior` still preserves its legacy compatibility `run(agent, message, intent)` entry path for tests and existing callers, but its repository boundary is now canonical.
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Focused regression suite recorded.
  Baseline evidence: pre-edit source audit confirmed the listed regressions and the branch was clean before work.
  Focused post-fix results:
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_behavior_contract_coordinator.py::test_dependency_prerequisite_planner_sends_reasoning_request_boundary tests/development/test_behavior_contract_coordinator.py::test_behavior_contract_run_state_round_trip_preserves_binding_resources tests/behaviors/test_execute_tests_behavior.py tests/behaviors/test_spec_behavior_boundaries.py tests/development/test_coordinator.py::test_coordination_snapshot_preserves_none_binding_fields_and_resources tests/development/test_tdd_coordinator.py::test_state_persists_repository_environment_resources tests/execution/test_rack_ai_work_unit_contract.py::test_repository_binding_round_trip_preserves_optional_fields_and_resources tests/integration/test_spec_to_tickets_flow.py::test_spec_finalization_triggers_architect tests/integration/test_spec_to_tickets_flow.py::test_full_workflow_spec_to_tickets tests/integration/test_spec_to_tickets_flow.py::test_spec_approval_metadata_saved`
  - Result: `14 passed`.
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/behaviors/test_analyze_spec_behavior.py`
  - Result: `6 passed`.
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

- [x] Final validation suite recorded.
  Results:
  - `./.venv/bin/python scripts/check_coding_principles.py` -> `coding principles gate passed`
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q` -> `208 passed`
  - `./.venv/bin/python -m compileall athba core llm_service tests scripts` -> passed
  - `git diff --check` -> passed
  - `git status --short --branch` before commit showed only the intended branch worktree changes
  Commit SHA: 7f1b349976dfa5fe5f2962a0c6cb003cf80f304f

INCOMPLETE_ITEMS = NONE
