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
  Commit SHA: `WORKTREE`
- [x] Read mandatory inputs before editing.
  Target responsibility: architectural and coding-principle compliance.
  Implementation evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the current PR17 description, `docs/pr17-specification-gatekeeper.md`, `scripts/check_coding_principles.py`, and the Session 1-3 ledgers before code changes.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Inventory current module sizes, classes/functions, responsibility boundaries, persistence surfaces, and callers before refactor.
  Target responsibility: exact pre-refactor orchestration map.
  Implementation evidence: `tdd_coordinator.py` is `15199` bytes / `385` lines; `coordinator.py` is `8961` bytes / `229` lines. Current public classes/functions and importers are recorded below.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Identify active, compatibility, and obsolete orchestration responsibilities before changing structure.
  Target responsibility: preserve the authoritative PR17 path and avoid caller churn.
  Implementation evidence: the active PR17 path is `BehaviorContractCoordinator`, which consumes TDD phase execution semantics and the `TddStateRepository` protocol but does not instantiate `TddCoordinator` or `DevelopmentCoordinator`. `TddCoordinator` and `DevelopmentCoordinator` are compatibility/legacy entrypoints with direct test callers. No obsolete deletion candidate is safe in Session 4 because public imports and persistence types still exist.
  Tests: `rg -n "DevelopmentCoordinator|TddCoordinator|TddStateRepository" tests core scripts`.
  Commit SHA: `WORKTREE`
- [x] Run focused baseline tests before refactor.
  Target responsibility: establish the current orchestration baseline.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_tdd_coordinator.py tests/development/test_coordinator.py tests/development/test_behavior_contract_coordinator.py` passed with `80 passed`.
  Tests: `tests/development/test_tdd_coordinator.py`, `tests/development/test_coordinator.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [ ] Decompose shared TDD phase execution semantics into a focused module used by the active PR17 path and compatibility TDD coordinator.
  Target responsibility: shared RED/GREEN execution semantics without private helper imports from a compatibility module.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Decompose legacy TDD coordination into small collaborators while preserving `core.development.tdd_coordinator` import compatibility.
  Target responsibility: compatibility orchestration facade over cohesive state/workflow collaborators.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Decompose legacy tiny-ticket coordination into small collaborators while preserving `core.development.coordinator` import compatibility.
  Target responsibility: compatibility orchestration facade over cohesive sequential work-unit collaborators.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Extend `scripts/check_coding_principles.py` to cover all Session 4 changed/new application classes without broad exemptions.
  Target responsibility: machine enforcement for the orchestration refactor scope.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Run post-refactor focused tests.
  Target responsibility: prove local behavior preservation for active and compatibility coordinators.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Run full suite.
  Target responsibility: prove repository-wide compatibility.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Run compileall.
  Target responsibility: import and syntax integrity.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Run `git diff --check`.
  Target responsibility: patch hygiene.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Confirm `legacy` remains unchanged and push all Session 4 commits to PR17.
  Target responsibility: branch integrity and publication.
  Implementation evidence: pending.
  Tests: pending.
  Commit SHA: `PENDING`
- [ ] Finalize this ledger with `INCOMPLETE_ITEMS = NONE` only after every mandatory item is complete.
  Target responsibility: authoritative Session 4 record.
  Implementation evidence: pending.
  Tests: N/A.
  Commit SHA: `PENDING`

## Current module sizes and structure

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

## Responsibility map

- Active PR17 orchestration
  - `core/development/behavior_contract_coordinator.py`
  - Owns the authoritative contract-driven development lane.
  - Currently imports TDD phase outcome helpers and `TddStateRepository` from `core.development.tdd_coordinator`.
- Compatibility TDD orchestration
  - `core/development/tdd_coordinator.py`
  - Runs a predefined RED/GREEN cycle per `TddBehavior`.
  - Persists `TddSnapshot`.
  - Builds tester/developer work units.
  - Owns shared phase execution/value helpers that the active PR17 path should not source from a compatibility module.
- Compatibility tiny-ticket orchestration
  - `core/development/coordinator.py`
  - Runs dependency-aware work units one at a time.
  - Persists `CoordinationSnapshot`.
  - Advances the trusted base revision only on accepted results.

## Active, compatibility, and obsolete classification

- Active
  - Shared TDD phase execution semantics currently embedded in `tdd_coordinator.py` and consumed by `BehaviorContractCoordinator`.
  - `TddStateRepository` protocol because the active contract-run store depends on it.
- Compatibility
  - `TddCoordinator`
  - `TesterWorkUnitFactory`
  - `DeveloperWorkUnitFactory`
  - `DevelopmentCoordinator`
  - `CoordinationStateRepository`
- Obsolete after extraction
  - Private helper ownership inside `tdd_coordinator.py` for phase execution semantics.
  - Monolithic persistence/execution/result assembly inside both coordinator classes.

## Current persistence surfaces to preserve

- `TddSnapshot.to_dict` / `from_dict`
- `CoordinationSnapshot.to_dict` / `from_dict`
- `ExecutionAttemptRecord.to_dict` / `from_dict`
- `WorkUnitProgress.to_dict` / `from_dict`
- `TddBehaviorProgress.to_dict` / `from_dict`
- `TddPhaseState.to_dict` / `from_dict`
- `ContractRunStore.load` / `save` / `initial`
- `TddStateRepo.load` / `save`
- `WorkUnitStateRepo.load` / `save`

## Public callers and importers

- `core/development/behavior_contract_coordinator.py`
  - Imports `RED_ALREADY_SATISFIED_FRAGMENT`, `TddStateRepository`, `_PhaseOutcome`, `_blocked_reason_for_result`, `_is_red_already_satisfied`, and `_phase_state_from_result`
- `core/development/contract_run_store.py`
  - Imports `TddStateRepository`
- `tests/development/test_tdd_coordinator.py`
  - Imports `TddCoordinator`, `TesterWorkUnitFactory`, `DeveloperWorkUnitFactory`
- `tests/development/test_coordinator.py`
  - Imports `DevelopmentCoordinator`
- `core/datastore/repos/tdd_state_repo.py`
  - Loads and saves `TddSnapshot`
- `core/datastore/repos/work_unit_state_repo.py`
  - Loads and saves `CoordinationSnapshot`

## Current focused baseline behavior

- `tests/development/test_tdd_coordinator.py`
  - Covers RED before GREEN ordering, accepted revision progression, blocked RED/GREEN handling, already-satisfied RED semantics, missing revision fail-closed semantics, work-unit path isolation, state persistence, resume behavior, and transport failures.
- `tests/development/test_coordinator.py`
  - Covers dependency progression, rejected/blocked/transport failure behavior, missing accepted revision fail-closed semantics, resume behavior, and snapshot round-trip persistence.
- `tests/development/test_behavior_contract_coordinator.py`
  - Covers the active PR17 path that reuses TDD phase execution semantics and TDD snapshot persistence.
- Baseline result on 2026-08-30
  - `80 passed` for the focused orchestration suite above.

## Current coding-principle violations

- `core/development/tdd_coordinator.py:TddCoordinator`
  - `247` executable lines
  - `__init__` has `5` inputs
  - `_block_and_save` has `8` inputs
  - `_save_snapshot` has `5` inputs
  - mixed responsibility: orchestration, persistence, phase execution, result assembly, and compatibility exports
- `core/development/coordinator.py:DevelopmentCoordinator`
  - `175` executable lines
  - `__init__` has `3` inputs
  - mixed responsibility: orchestration, persistence, attempt recording, block/result assembly, and resume behavior

## Planned target modules

- `core/development/tdd_phase_execution.py`
  - Responsibility: shared RED/GREEN execution request/result types, transport failure state, accepted/non-accepted phase semantics, and stable status helpers
- `core/development/tdd_cycle_coordination.py`
  - Responsibility: compatibility TDD coordination, phase progression state, and TDD snapshot persistence helpers
- `core/development/work_unit_coordination.py`
  - Responsibility: compatibility sequential work-unit coordination and `CoordinationSnapshot` persistence helpers
- `core/development/tdd_coordinator.py`
  - Responsibility: compatibility facade and re-exports only
- `core/development/coordinator.py`
  - Responsibility: compatibility facade and re-exports only

INCOMPLETE_ITEMS = PRESENT
