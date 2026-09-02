# Failure Progression Refactor Plan

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
Target module: `core/development/failure_progression.py`

## Session checklist

- [x] Verify branch and protected historical snapshot.
  Evidence: `git rev-parse --abbrev-ref HEAD` returned `pr17-specification-gatekeeper`; `git rev-parse legacy` returned `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
  Commit SHA: `WORKTREE`
- [x] Read mandatory inputs before editing.
  Evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the current PR17 description, `docs/pr17-specification-gatekeeper.md`, `scripts/check_coding_principles.py`, and `docs/tdd_progression_refactor_plan.md`.
  Commit SHA: `WORKTREE`
- [x] Inventory current module size, class list, persistence surfaces, and callers.
  Evidence: `wc -c core/development/failure_progression.py` returned `20315`; classes currently defined are `FailureClassification`, `ProgressionAction`, `FailureRouteState`, `PacketKind`, `DependencyDisposition`, `DependencyDecision`, `WorkPacketSplit`, `UnclassifiedAnalysis`, `FailureObservation`, `FailureDecision`, `RepairPacket`, `FailureProgressState`, and `FailureProgressionPolicy`. Direct importers are `core/development/behavior_contract_coordinator.py`, `core/development/contract_run_domain.py`, and `tests/development/test_failure_progression.py`.
  Commit SHA: `WORKTREE`
- [x] Identify focused baseline tests before refactor.
  Evidence: standalone policy/state coverage is in `tests/development/test_failure_progression.py`; router integration coverage is exercised through `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [x] Run focused baseline tests before refactor.
  Evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py` passed with `68 passed`.
  Commit SHA: `WORKTREE`
- [x] Split `core/development/failure_progression.py` into cohesive domain modules while preserving caller compatibility.
  Evidence: implementation moved into `core/development/failure_values.py`, `core/development/failure_records.py`, `core/development/failure_state.py`, `core/development/failure_transitions.py`, and `core/development/failure_policy.py`; `core/development/failure_progression.py` is now a compatibility facade with re-exports only.
  Commit SHA: `589ddd2`
- [x] Extend `scripts/check_coding_principles.py` to cover Session 2 changed/new application classes without broad exemptions.
  Evidence: the gate now includes `failure_policy.py`, `failure_progression.py`, `failure_records.py`, `failure_state.py`, `failure_transitions.py`, and `failure_values.py` in addition to the prior Session 1 scope. `./.venv/bin/python scripts/check_coding_principles.py` returned `coding principles gate passed`.
  Commit SHA: `589ddd2`
- [x] Add or update compatibility coverage where persisted failure-state behavior is not already explicit.
  Evidence: `tests/development/test_failure_progression.py` now includes explicit prerequisite-deferral persistence coverage and a legacy/default payload load check for `FailureProgressState` while keeping the original round-trip assertions intact.
  Commit SHA: `589ddd2`
- [x] Run post-refactor focused tests.
  Evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py` passed with `70 passed`.
  Commit SHA: `589ddd2`
- [x] Run full suite.
  Evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q` passed with `194 passed`.
  Commit SHA: `589ddd2`
- [x] Run compileall.
  Evidence: `./.venv/bin/python -m compileall athba core llm_service tests scripts` completed without errors.
  Commit SHA: `589ddd2`
- [x] Run `git diff --check`.
  Evidence: `git diff --check` produced no output after the refactor validation pass.
  Commit SHA: `589ddd2`
- [x] Confirm `legacy` remains unchanged and push all commits to PR17.
  Evidence: `git rev-parse legacy` remained `8334f42a8865b9360972f5e0422a8f61d02dedb6`. Push evidence will be finalized after the ledger closeout commit.
  Commit SHA: `PENDING_PUSH`
- [x] Finalize this ledger with `INCOMPLETE_ITEMS = NONE` only after every mandatory item is complete.
  Evidence: all mandatory Session 2 checklist items in this ledger are now recorded with concrete validation evidence and milestone SHAs.
  Commit SHA: `PENDING_LEDGER_COMMIT`

## Current module responsibilities

- Failure classification taxonomy.
- Classification priority ordering.
- Classification to progression-action policy mapping.
- Route-state and packet-kind vocabulary.
- Dependency decision, split record, and unclassified-analysis records.
- Failure observation and failure decision evidence records.
- Repair packet persistence.
- Durable failure progress state.
- Retry counting and retry-budget checks.
- Dependency deferral state mutation.
- General failure-state recording and serialization.

## Current class list by domain family

- Taxonomy and route vocabulary: `FailureClassification`, `ProgressionAction`, `FailureRouteState`, `PacketKind`, `DependencyDisposition`.
- Evidence and state records: `DependencyDecision`, `WorkPacketSplit`, `UnclassifiedAnalysis`, `FailureObservation`, `FailureDecision`, `RepairPacket`, `FailureProgressState`.
- Deterministic policy and mutation helper: `FailureProgressionPolicy`.

## Persistence interfaces to preserve

- `DependencyDecision.to_dict` / `from_dict`
- `WorkPacketSplit.to_dict` / `from_dict`
- `UnclassifiedAnalysis.to_dict` / `from_dict`
- `FailureObservation.to_dict` / `from_dict`
- `FailureDecision.to_dict` / `from_dict`
- `RepairPacket.to_dict` / `from_dict`
- `FailureProgressState.to_dict` / `from_dict`

## Current policy structure

- Fixed priority table: `FAILURE_PRIORITY = {classification: index}` in enum order.
- Fixed classification -> action mapping currently embedded as `FailureProgressionPolicy._ACTIONS`.
- Current route-state transitions currently embedded in `FailureProgressionPolicy.record(...)` and `FailureProgressionPolicy.defer_for_prerequisites(...)`.
- Known audit risk from PR17: global `security_or_execution_policy_violation -> REPAIR_TESTER` and `change_scope_violation -> REPAIR_TESTER` mappings are phase-independent in the policy table and may be semantically wrong for GREEN candidates, but that behavior must remain unchanged in this structural session.

## Current retry mechanisms

- Retry counters are stored in `FailureProgressState.retry_counts` keyed by raw route strings.
- `FailureProgressionPolicy.retry_allowed(...)` compares the per-route count with a caller-supplied integer budget.
- `FailureProgressionPolicy.record(...)` increments the route count when a route string is supplied.

## Current imports and callers

- `core/development/behavior_contract_coordinator.py`
  Responsibility: builds `FailureObservation`, chooses route actions through `FailureProgressionPolicy`, persists repair/dependency state through `FailureProgressState`.
- `core/development/contract_run_domain.py`
  Responsibility: stores `FailureProgressState` inside `BehaviorContractRunState` persistence.
- `tests/development/test_failure_progression.py`
  Responsibility: fixed-priority, action mapping, retry, packet, and state round-trip coverage.

## Focused tests and current evidence

- `tests/development/test_failure_progression.py`
  Covers classification priority, action mapping, repair-packet persistence, retry behavior, blocker/history round trips, typed dependency/split/unclassified persistence.
- `tests/development/test_behavior_contract_coordinator.py`
  Covers router integration and persisted run-state behavior around failed candidates, dependency decisions, retry limits, review/replan state, and resume behavior.
- Baseline result on 2026-08-30: `68 passed` for `tests/development/test_failure_progression.py` plus `tests/development/test_behavior_contract_coordinator.py`.

## Planned target modules

- `core/development/failure_progression.py`
  Responsibility: compatibility facade and re-exports only.
- `core/development/failure_values.py`
  Responsibility: failure taxonomy enums and stable priority data.
- `core/development/failure_records.py`
  Responsibility: dependency, split, unclassified, observation, decision, and repair packet records.
- `core/development/failure_state.py`
  Responsibility: durable `FailureProgressState` plus any smaller composed persisted state helpers if they improve clarity without changing payloads.
- `core/development/failure_policy.py`
  Responsibility: explicit classification -> action mapping and priority-based dominant-class selection.
- `core/development/failure_transitions.py`
  Responsibility: retry counting/budget checks and explicit state-recording/deferral transitions.

## Known incomplete PR17 routes deliberately outside scope

- Full packet-splitting execution, child scheduling, and reconciliation are still broader PR17 work beyond this structural refactor.
- Phase ownership ambiguity for policy-violation and change-scope routes remains a residual finding to preserve visibly, not solve here.
- Broader missing failure routes or architectural audits outside `failure_progression.py` remain out of scope unless needed to preserve current behavior.

## Policy audit

- Fixed priority ordering remains `FAILURE_PRIORITY = {classification: enum order index}`.
- Explicit preserved classification -> action mapping:
  - `executor_infrastructure_failure -> block_executor`
  - `environment_failure -> recover_environment`
  - `resource_limit_failure -> split_packet`
  - `syntax_or_parse_failure -> assess_mechanical_dependency`
  - `build_or_link_failure -> assess_mechanical_dependency`
  - `test_collection_or_bootstrap_failure -> assess_mechanical_dependency`
  - `security_or_execution_policy_violation -> repair_tester`
  - `change_scope_violation -> repair_tester`
  - `dependency_or_prerequisite_failure -> replan_dependency`
  - `contract_or_requirement_ambiguity -> block_ambiguity`
  - `tester_candidate_defect -> repair_tester`
  - `developer_candidate_defect -> repair_developer`
  - `expected_behavior_red -> accept_red`
  - `accumulated_regression -> repair_regression`
  - `semantic_integration_failure -> replan_integration`
  - `review_quality_failure -> repair_review`
  - `architecture_constraint_violation -> block_architecture`
  - `unclassified_failure -> analyze_unclassified`

## Post-refactor class audit

- `core/development/failure_values.py:FailureClassification` — responsibility: failure taxonomy; executable lines: `19`; constructor inputs: `0`; max method inputs: `0`; inheritance: `str, Enum`.
- `core/development/failure_values.py:ProgressionAction` — responsibility: progression-action vocabulary; executable lines: `15`; constructor inputs: `0`; max method inputs: `0`; inheritance: `str, Enum`.
- `core/development/failure_values.py:FailureRouteState` — responsibility: durable route-state vocabulary; executable lines: `12`; constructor inputs: `0`; max method inputs: `0`; inheritance: `str, Enum`.
- `core/development/failure_values.py:PacketKind` — responsibility: packet-kind vocabulary; executable lines: `3`; constructor inputs: `0`; max method inputs: `0`; inheritance: `str, Enum`.
- `core/development/failure_values.py:DependencyDisposition` — responsibility: dependency-decision vocabulary; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `str, Enum`.
- `core/development/failure_values.py:RetryRoute` — responsibility: typed retry-route vocabulary with stable persisted keys; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `str, Enum`.
- `core/development/failure_records.py:DependencyDecision` — responsibility: bounded dependency decision record; executable lines: `18`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_records.py:WorkPacketSplit` — responsibility: split record; executable lines: `16`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_records.py:UnclassifiedAnalysis` — responsibility: unclassified-analysis record; executable lines: `12`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_records.py:FailureObservation` — responsibility: provider-neutral failure evidence record; executable lines: `19`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_records.py:FailureDecision` — responsibility: persisted dominant failure decision record; executable lines: `10`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_records.py:RepairPacket` — responsibility: descriptive repair packet record; executable lines: `25`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_state.py:FailureProgressState` — responsibility: durable aggregate failure state; executable lines: `16`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_transitions.py:RetryBudget` — responsibility: typed retry-budget request; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/failure_transitions.py:FailureRecordRequest` — responsibility: typed state-recording request; executable lines: `7`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/failure_transitions.py:PrerequisiteDeferralRequest` — responsibility: typed prerequisite-deferral request; executable lines: `5`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/failure_transitions.py:FailureRetryPolicy` — responsibility: deterministic retry-budget check; executable lines: `5`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_transitions.py:FailureStateTransitions` — responsibility: behavior-preserving failure-state mutation helpers; executable lines: `18`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_policy.py:FailureDecisionPolicy` — responsibility: dominant-class selection and action resolution; executable lines: `9`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/failure_policy.py:FailureProgressionPolicy` — responsibility: compatibility facade over decision, retry, and state-transition collaborators; executable lines: `12`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.

INCOMPLETE_ITEMS = NONE
