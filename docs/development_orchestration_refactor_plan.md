# Development Orchestration Refactor Plan

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
Target modules:
- `core/development/tdd_coordinator.py`
- `core/development/coordinator.py`

## Session checklist

- [x] Verify branch and protected historical snapshot.
  Target responsibility: branch safety and historical boundary preservation.
  Implementation evidence: `git rev-parse --abbrev-ref HEAD` returned `pr17-specification-gatekeeper`; `git rev-parse legacy` returned `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
  Tests: N/A.
  Commit SHA: `1fe517b`
- [x] Read mandatory inputs before editing.
  Target responsibility: architectural and coding-principle compliance.
  Implementation evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the current PR17 description, `docs/pr17-specification-gatekeeper.md`, `scripts/check_coding_principles.py`, and the Session 1-3 ledgers before code changes.
  Tests: N/A.
  Commit SHA: `1fe517b`
- [x] Inventory current module sizes, classes/functions, responsibility boundaries, persistence surfaces, and callers before refactor.
  Target responsibility: exact pre-refactor orchestration map.
  Implementation evidence: `tdd_coordinator.py` was `15199` bytes / `385` lines; `coordinator.py` was `8961` bytes / `229` lines. Current public classes/functions and importers are recorded below.
  Tests: N/A.
  Commit SHA: `1fe517b`
- [x] Identify active, compatibility, and obsolete orchestration responsibilities before changing structure.
  Target responsibility: preserve the authoritative PR17 path and avoid caller churn.
  Implementation evidence: the active PR17 path is `BehaviorContractCoordinator`, which consumes TDD phase execution semantics and the `TddStateRepository` protocol but does not instantiate `TddCoordinator` or `DevelopmentCoordinator`. `TddCoordinator` and `DevelopmentCoordinator` are compatibility entrypoints with direct test callers. No safe deletion candidate existed in Session 4 because public imports and persistence types remain live.
  Tests: `rg -n "DevelopmentCoordinator|TddCoordinator|TddStateRepository" tests core scripts`.
  Commit SHA: `1fe517b`
- [x] Run focused baseline tests before refactor.
  Target responsibility: establish the current orchestration baseline.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_tdd_coordinator.py tests/development/test_coordinator.py tests/development/test_behavior_contract_coordinator.py` passed with `80 passed`.
  Tests: `tests/development/test_tdd_coordinator.py`, `tests/development/test_coordinator.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `1fe517b`
- [x] Decompose shared TDD phase execution semantics into a focused module used by the active PR17 path and compatibility TDD coordinator.
  Target responsibility: shared RED/GREEN execution semantics without private helper imports from a compatibility module.
  Implementation evidence: created `core/development/tdd_phase_execution.py` for `PhaseExecutionRequest`, `PhaseOutcome`, `TddPhaseExecutor`, transport-failure state construction, RED already-satisfied detection, and stable blocked-reason/status helpers. `BehaviorContractCoordinator` now imports these semantics directly.
  Tests: `tests/development/test_tdd_coordinator.py`, `tests/development/test_behavior_contract_coordinator.py`, `scripts/check_coding_principles.py`.
  Commit SHA: `1fe517b`
- [x] Decompose legacy TDD coordination into small collaborators while preserving `core.development.tdd_coordinator` import compatibility.
  Target responsibility: compatibility orchestration facade over cohesive state/workflow collaborators.
  Implementation evidence: created `core/development/tdd_cycle_coordination.py` for `TddCoordinator`, factories, state protocol, and snapshot/result helpers. `core/development/tdd_coordinator.py` is now a compatibility facade with re-exports and a compatibility wrapper for `_phase_state_from_result`.
  Tests: `tests/development/test_tdd_coordinator.py`.
  Commit SHA: `1fe517b`
- [x] Decompose legacy tiny-ticket coordination into small collaborators while preserving `core.development.coordinator` import compatibility.
  Target responsibility: compatibility orchestration facade over cohesive sequential work-unit collaborators.
  Implementation evidence: created `core/development/work_unit_coordination.py` for `DevelopmentCoordinator`, state protocol, progression context, and snapshot persistence helpers. `core/development/coordinator.py` is now a compatibility facade with re-exports only.
  Tests: `tests/development/test_coordinator.py`.
  Commit SHA: `1fe517b`
- [x] Extend `scripts/check_coding_principles.py` to cover all Session 4 changed/new application classes without broad exemptions.
  Target responsibility: machine enforcement for the orchestration refactor scope.
  Implementation evidence: added `tdd_phase_execution.py`, `tdd_cycle_coordination.py`, and `work_unit_coordination.py` to the AST gate target list while preserving prior Session 1-3 coverage.
  Tests: `./.venv/bin/python scripts/check_coding_principles.py` returned `coding principles gate passed`.
  Commit SHA: `1fe517b`
- [x] Run post-refactor focused tests.
  Target responsibility: prove local behavior preservation for active and compatibility coordinators.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_tdd_coordinator.py tests/development/test_coordinator.py tests/development/test_behavior_contract_coordinator.py` passed with `80 passed`.
  Tests: `tests/development/test_tdd_coordinator.py`, `tests/development/test_coordinator.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `1fe517b`
- [x] Run full suite.
  Target responsibility: prove repository-wide compatibility.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q` passed with `196 passed`.
  Tests: full ATHBA suite.
  Commit SHA: `1fe517b`
- [x] Run compileall.
  Target responsibility: import and syntax integrity.
  Implementation evidence: `./.venv/bin/python -m compileall athba core llm_service tests scripts` completed without errors.
  Tests: `./.venv/bin/python -m compileall athba core llm_service tests scripts`.
  Commit SHA: `1fe517b`
- [x] Run `git diff --check`.
  Target responsibility: patch hygiene.
  Implementation evidence: `git diff --check` produced no output after the Session 4 refactor.
  Tests: `git diff --check`.
  Commit SHA: `1fe517b`
- [x] Confirm `legacy` remains unchanged and push all Session 4 commits to PR17.
  Target responsibility: branch integrity and publication.
  Implementation evidence: `git rev-parse legacy` remained `8334f42a8865b9360972f5e0422a8f61d02dedb6`; Session 4 commits are listed below and are pushed on `origin/pr17-specification-gatekeeper` after this ledger finalization.
  Tests: `git rev-parse legacy`, `git push origin pr17-specification-gatekeeper`.
  Commit SHA: `1fe517b`
- [x] Finalize this ledger with `INCOMPLETE_ITEMS = NONE` only after every mandatory item is complete.
  Target responsibility: authoritative Session 4 record.
  Implementation evidence: this ledger now records the active-versus-compatibility split, the resulting module ownership, the class audit, the focused and full validation results, the clean diff state, and the preserved legacy snapshot.
  Tests: N/A.
  Commit SHA: `1fe517b`

## Before

- `core/development/tdd_coordinator.py`
  - Size: `15199` bytes
  - Lines: `385`
  - Classes: `TddCoordinationResult`, `TddStateRepository`, `TesterWorkUnitFactory`, `DeveloperWorkUnitFactory`, `TddCoordinator`, `_PhaseOutcome`
  - Helpers/constants: `RED_ALREADY_SATISFIED_FRAGMENT`, `_phase_state_from_result`, `_phase_status_for_result`, `_blocked_reason_for_result`, `_is_red_already_satisfied`, `_utc_now`
- `core/development/coordinator.py`
  - Size: `8961` bytes
  - Lines: `229`
  - Classes: `CoordinationResult`, `CoordinationStateRepository`, `DevelopmentCoordinator`
  - Helpers/constants: `_TERMINAL_STATUSES`, `_terminal_status_for_result`, `_utc_now`
- Active dependency problem
  - `BehaviorContractCoordinator` imported private phase-execution helpers and the TDD state-repository protocol from `core.development.tdd_coordinator`.
- Coding-principle violations
  - `TddCoordinator` was `247` executable lines and had an explicit `__init__` with `5` inputs.
  - `DevelopmentCoordinator` was `175` executable lines and had an explicit `__init__` with `3` inputs.
  - Both coordinators mixed orchestration, persistence, result assembly, and compatibility concerns.

## After

- `core/development/tdd_phase_execution.py`
  - Size: `4831` bytes
  - Responsibility: shared RED/GREEN execution request/result types, transport failure state, accepted/non-accepted phase semantics, and stable status helpers.
- `core/development/tdd_cycle_coordination.py`
  - Size: `13287` bytes
  - Responsibility: compatibility TDD coordination, factory ownership, snapshot/result helpers, and ordered RED/GREEN progression.
- `core/development/work_unit_coordination.py`
  - Size: `9828` bytes
  - Responsibility: compatibility sequential work-unit coordination, dependency-ready selection, attempt capture, and `CoordinationSnapshot` persistence helpers.
- `core/development/tdd_coordinator.py`
  - Size: `2042` bytes
  - Responsibility: compatibility facade and re-exports for legacy imports.
- `core/development/coordinator.py`
  - Size: `321` bytes
  - Responsibility: compatibility facade and re-exports for legacy imports.
- Active path ownership
  - `BehaviorContractCoordinator` now imports phase execution semantics from `core.development.tdd_phase_execution` and the state-repository protocol from `core.development.tdd_cycle_coordination` instead of importing private helpers from the compatibility facade.

## Persistence surfaces preserved

- `TddSnapshot.to_dict` / `from_dict`
- `CoordinationSnapshot.to_dict` / `from_dict`
- `ExecutionAttemptRecord.to_dict` / `from_dict`
- `WorkUnitProgress.to_dict` / `from_dict`
- `TddBehaviorProgress.to_dict` / `from_dict`
- `TddPhaseState.to_dict` / `from_dict`
- `ContractRunStore.load` / `save` / `initial`
- `TddStateRepo.load` / `save`
- `WorkUnitStateRepo.load` / `save`

## Public callers and compatibility

- `core/development/behavior_contract_coordinator.py`
  - Uses the extracted phase execution module directly.
- `core/development/contract_run_store.py`
  - Uses `TddStateRepository` from `core.development.tdd_cycle_coordination`.
- `tests/development/test_tdd_coordinator.py`
  - Still imports `TddCoordinator`, `TesterWorkUnitFactory`, and `DeveloperWorkUnitFactory` from `core.development.tdd_coordinator`.
- `tests/development/test_coordinator.py`
  - Still imports `DevelopmentCoordinator` from `core.development.coordinator`.
- Compatibility facades
  - `core/development/tdd_coordinator.py`
  - `core/development/coordinator.py`

## Class audit

- `core/development/tdd_phase_execution.py:PhaseExecutionRequest`
  - Responsibility: typed phase execution request.
  - Executable lines: `4`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/tdd_phase_execution.py:PhaseOutcome`
  - Responsibility: typed phase execution result.
  - Executable lines: `6`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/tdd_phase_execution.py:TddPhaseExecutor`
  - Responsibility: execute one RED/GREEN work unit and translate Rack AI results into stable TDD phase state.
  - Executable lines: `17`
  - Constructor inputs: `1`
  - Max method inputs: `1`
  - Inheritance: `composition-only`
- `core/development/tdd_cycle_coordination.py:TddCoordinationResult`
  - Responsibility: compatibility TDD coordination result record.
  - Executable lines: `9`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/tdd_cycle_coordination.py:TddStateRepository`
  - Responsibility: TDD snapshot persistence protocol.
  - Executable lines: `5`
  - Constructor inputs: `0`
  - Max method inputs: `1`
  - Inheritance: `Protocol`
- `core/development/tdd_cycle_coordination.py:TesterWorkUnitFactory`
  - Responsibility: RED work-unit construction.
  - Executable lines: `3`
  - Constructor inputs: `0`
  - Max method inputs: `1`
  - Inheritance: `composition-only`
- `core/development/tdd_cycle_coordination.py:DeveloperWorkUnitFactory`
  - Responsibility: GREEN work-unit construction.
  - Executable lines: `3`
  - Constructor inputs: `0`
  - Max method inputs: `1`
  - Inheritance: `composition-only`
- `core/development/tdd_cycle_coordination.py:TddCoordinatorDependencies`
  - Responsibility: compatibility TDD coordinator dependency bundle.
  - Executable lines: `6`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/tdd_cycle_coordination.py:TddCoordinationContext`
  - Responsibility: mutable progression snapshot carried through RED/GREEN execution.
  - Executable lines: `6`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/tdd_cycle_coordination.py:TddCoordinator`
  - Responsibility: compatibility facade over TDD progression helpers.
  - Executable lines: `5`
  - Constructor inputs: `2`
  - Max method inputs: `2`
  - Inheritance: `composition-only`
- `core/development/work_unit_coordination.py:CoordinationResult`
  - Responsibility: compatibility sequential coordination result record.
  - Executable lines: `8`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/work_unit_coordination.py:CoordinationStateRepository`
  - Responsibility: sequential work-unit snapshot persistence protocol.
  - Executable lines: `5`
  - Constructor inputs: `0`
  - Max method inputs: `1`
  - Inheritance: `Protocol`
- `core/development/work_unit_coordination.py:DevelopmentCoordinatorDependencies`
  - Responsibility: compatibility sequential coordinator dependency bundle.
  - Executable lines: `4`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/work_unit_coordination.py:CoordinationContext`
  - Responsibility: sequential work-unit progression snapshot.
  - Executable lines: `6`
  - Constructor inputs: `0`
  - Max method inputs: `0`
  - Inheritance: `composition-only`
- `core/development/work_unit_coordination.py:DevelopmentCoordinator`
  - Responsibility: compatibility facade over sequential work-unit progression helpers.
  - Executable lines: `5`
  - Constructor inputs: `2`
  - Max method inputs: `2`
  - Inheritance: `composition-only`

## Validation evidence

- Coding gate
  - `./.venv/bin/python scripts/check_coding_principles.py`
  - Result: `coding principles gate passed`
- Focused orchestration suite
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_tdd_coordinator.py tests/development/test_coordinator.py tests/development/test_behavior_contract_coordinator.py`
  - Result: `80 passed`
- Full ATHBA suite
  - `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q`
  - Result: `196 passed`
- Compile validation
  - `./.venv/bin/python -m compileall athba core llm_service tests scripts`
  - Result: passed
- Diff hygiene
  - `git diff --check`
  - Result: no output
- Legacy snapshot
  - `git rev-parse legacy`
  - Result: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Milestone commits

- `1fe517b` `refactor: rationalize development orchestration`

INCOMPLETE_ITEMS = NONE
