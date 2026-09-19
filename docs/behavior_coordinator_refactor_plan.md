# Behavior Coordinator Refactor Ledger

Baseline:
- `BehaviorContractCoordinator` was 597 executable-span lines in the original gate output.
- `BehaviorContractCoordinator.__init__` had 20 inputs.
- Oversized collaborator methods remained across planning, review, work-unit construction, and failure routing.

Completed responsibilities:
- responsibility: authoritative run-state loading
  target class/module: `ContractRunStore` / `core/development/contract_run_store.py`
  tests: `tests/development/test_behavior_contract_coordinator.py`, `tests/development/test_specification_gatekeeper.py`
  completion evidence: `BehaviorContractCoordinator` now loads snapshots through `ContractRunStore` and resumes from persisted `run_state.contract`.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: run-state persistence
  target class/module: `ContractRunStore` / `core/development/contract_run_store.py`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: every progression step persists through `ContractRunStore.save` before the loop continues or returns.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: state/pool transition coordination
  target class/module: `BehaviorContractCoordinator`, `ReadyPoolProgressor`, `CycleActiveProgressor`, `ReviewReadyProgressor`, `RepairReadyProgressor`
  tests: `tests/development/test_behavior_contract_coordinator.py`, `tests/development/test_specification_gatekeeper.py`
  completion evidence: pool-specific progression is delegated to focused collaborators and the coordinator is a facade.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: TDD-ready scheduling
  target class/module: `ReadyPoolProgressor`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: step selection and completion handling are isolated in `ReadyPoolProgressor`.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: RED phase execution
  target class/module: `CycleActiveProgressor`, `PhaseExecutor`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: RED execution builds typed work-unit requests and executes through `PhaseExecutor`.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: GREEN phase execution
  target class/module: `CycleActiveProgressor`, `PhaseExecutor`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: GREEN execution is isolated from scheduling and review progression.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: failure observation construction
  target class/module: `FailureObservationBuilder`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: failure-observation synthesis is separated from routing and phase execution.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: failure classification/routing
  target class/module: `FailedCandidateRouter`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: dominant-failure routing, retry policy, and terminal replanning are delegated to `FailedCandidateRouter`.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: Tester repair progression
  target class/module: `FailedCandidateRouter`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: tester repair retries are policy-driven and preserved in failure progress state.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: Developer repair progression
  target class/module: `FailedCandidateRouter`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: developer repair retries remain bounded and resume from the trusted revision.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: environment recovery progression
  target class/module: `FailedCandidateRouter`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: environment recovery remains a separate route that reactivates the cycle only after a health proof.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: dependency/prerequisite recovery
  target class/module: `FailedCandidateRouter`, `DependencyPrerequisitePlanner`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: dependency defer/replan decisions are delegated through typed dependency-decision requests.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: synthesized prerequisite handling
  target class/module: `_add_synthesized_prerequisite`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: synthesized prerequisite insertion remains persisted in `run_state.contract` and survives resume.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: Senior Review progression
  target class/module: `ReviewReadyProgressor`, `SeniorReviewer`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: review orchestration and semantic review prompting are isolated from phase execution.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: semantic repair progression
  target class/module: `RepairReadyProgressor`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: repair execution and return-to-review progression are isolated from ordinary GREEN execution.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: Gatekeeper progression
  target class/module: `ReadyPoolProgressor`, `ReviewReadyProgressor`
  tests: `tests/development/test_specification_gatekeeper.py`
  completion evidence: targeted gap selection, re-entry, and targeted checklist reassessment are delegated outside the coordinator facade.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: trusted revision progression
  target class/module: `ReviewReadyProgressor`, `ContractRunStore`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: approved candidate revisions become the semantic base and persisted repository binding through focused progression objects.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: completion progression
  target class/module: `ReadyPoolProgressor`, `ReviewReadyProgressor`
  tests: `tests/development/test_behavior_contract_coordinator.py`, `tests/development/test_specification_gatekeeper.py`
  completion evidence: completion and approval exits are centralized in pool-specific progressors and preserve ordered completed requirement refs.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: persisted contract authoritative on resume
  target class/module: `BehaviorContractCoordinator`, `ContractRunStore`
  tests: `tests/development/test_behavior_contract_coordinator.py`
  completion evidence: the loop rebinds `contract = run_state.contract` on every iteration and all targeted-gap/prerequisite mutations persist in snapshot state.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: coordinator reduced to small facade
  target class/module: `BehaviorContractCoordinator`
  tests: `scripts/check_coding_principles.py`
  completion evidence: the coordinator now delegates all pool progression to focused collaborators and only loads, dispatches, persists, and returns.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: coding-principle class-size audit
  target class/module: `scripts/check_coding_principles.py`
  tests: `python3 scripts/check_coding_principles.py`
  completion evidence: the AST gate now checks executable class lines and method input counts for the changed coordinator modules.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: coding-principle parameter audit
  target class/module: `core/development/behavior_contract_coordinator.py`
  tests: `python3 scripts/check_coding_principles.py`
  completion evidence: long collaborator signatures were replaced with typed request/context objects or reduced facade inputs.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`
- responsibility: full behavior-preservation regression
  target class/module: repository-wide
  tests: `DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q`
  completion evidence: full repository suite passed on 2026-08-30 after the refactor.
  commit sha: `3a5abbc74a542222a025b3daa300956b6e59dab7`

INCOMPLETE_ITEMS = NONE
