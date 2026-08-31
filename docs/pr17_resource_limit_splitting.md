# PR17 Resource-Limit Splitting

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`
Protected legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Checklist

- [x] Verify branch, clean baseline, and protected legacy snapshot.
  - Design target: operate only on ATHBA `/srv/ATHBA`, keep `legacy` unchanged, and continue on `pr17-specification-gatekeeper`.
  - Evidence: `git status --short --branch` was clean before Phase 2 edits and `git rev-parse legacy` returned `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
  - Tests: N/A
  - Commit SHA: `54efdde`

- [x] Read mandatory inputs and verify current split behavior before editing.
  - Design target: confirm how `resource_limit_failure`, `split_packet`, `WorkPacketSplit`, `split_children`, and `split_required` behave at HEAD.
  - Evidence: read `AGENTS.md`, `agent.MD`, `coding_principles.MD`, `docs/pr17-specification-gatekeeper.md`, `docs/pr17_failure_transition_matrix.md`, `docs/pr17_failure_state_machine_unification.md`, `docs/ATHBA_RACK_AI_ARCHITECTURE.md`, the pre-PR17 ledgers, current failure modules, coordinator, work-unit code, and focused tests. Verified that current production routing stops at `split_required` without split planning or child execution.
  - Tests: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_failure_progression.py tests/development/test_behavior_contract_coordinator.py`
  - Commit SHA: `54efdde`

- [x] Define bounded split planner contract and split bounds.
  - Design target: add a provider-neutral planner with explicit `split` or `cannot_split`, maximum 2 children, and maximum split depth 2.
  - Evidence: `core/development/resource_split.py` now owns `ResourceLimitSplitPlanner`, `ResourceSplitPlannerRequest`, `ResourceSplitDecision`, `SplitDecisionStatus`, and explicit bounds `MAX_SPLIT_CHILDREN = 2`, `MAX_SPLIT_DEPTH = 2`. Invalid or unsafe split payloads fail closed to replan.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_cannot_split_resource_limit_failure_replans_without_child_work`; `tests/development/test_behavior_contract_coordinator.py::test_split_depth_exhaustion_replans_without_calling_split_planner`
  - Commit SHA: `54efdde`

- [x] Persist split lineage and child definitions durably.
  - Design target: evolve `WorkPacketSplit`, `FailureProgressState.splits`, and `split_children` to preserve parent lineage, requirement traceability, child ordering, rationale, depth, and trusted revision.
  - Evidence: `core/development/failure_records.py` adds durable `SplitChildStep` and evolves `WorkPacketSplit` to persist `parent_step_id`, `parent_requirement_ref`, `trusted_revision`, `split_depth`, `child_steps`, and `completed_child_ids` while preserving legacy child-id payload compatibility. `core/development/failure_transitions.py` now writes split lineage through `SplitRecordRequest`.
  - Tests: `tests/development/test_failure_progression.py::test_split_record_round_trips_child_steps_and_completed_lineage`; `tests/development/test_behavior_contract_coordinator.py::test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision`
  - Commit SHA: `54efdde`

- [x] Re-enter split children through the normal TDD path.
  - Design target: schedule persisted split children through existing `tdd_ready -> cycle_active -> review_ready` progression without bypassing RED/GREEN/review.
  - Evidence: `ReadyPoolProgressor.advance()` now schedules the next persisted split child before normal planning. Split children become ordinary `ContractCycleRecord` entries and execute through the existing RED/GREEN/review pipeline.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision`; `tests/development/test_behavior_contract_coordinator.py::test_resume_split_uses_persisted_children_without_replanning`
  - Commit SHA: `54efdde`

- [x] Preserve parent completion semantics.
  - Design target: parent requirement stays incomplete until all required split children are semantically approved.
  - Evidence: `approval_resolution()` records child completion into persisted split lineage and only promotes the parent requirement into `completed_requirement_refs` once all split children are approved.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision`
  - Commit SHA: `54efdde`

- [x] Preserve trusted revision progression across child approvals and resumes.
  - Design target: each child starts from the correct trusted revision; later children use updated trusted revisions from earlier approved children.
  - Evidence: Split creation persists the split trusted revision, the first child schedules from that saved base, RED now executes from `cycle.base_revision`, and later siblings fall back to the latest `run_state.semantic_base_revision` after prior child approval.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_resource_limit_failure_splits_into_persisted_children_and_updates_trusted_revision`; `tests/development/test_behavior_contract_coordinator.py::test_resume_split_uses_persisted_children_without_replanning`
  - Commit SHA: `54efdde`

- [x] Bound nested split behavior and cannot-split failure handling.
  - Design target: depth exhaustion and malformed or unsafe split plans fail closed without repeated replanning on resume.
  - Evidence: `split_depth_for_step()` and `MAX_SPLIT_DEPTH` bound nesting. `_split_transition()` converts `cannot_split` and invalid planner payloads into `replan_ready` without creating child work; resume from persisted split state does not regenerate planner calls.
  - Tests: `tests/development/test_behavior_contract_coordinator.py::test_cannot_split_resource_limit_failure_replans_without_child_work`; `tests/development/test_behavior_contract_coordinator.py::test_split_depth_exhaustion_replans_without_calling_split_planner`; `tests/development/test_behavior_contract_coordinator.py::test_resume_split_uses_persisted_children_without_replanning`
  - Commit SHA: `54efdde`

- [x] Update matrix, validation evidence, and milestone commits.
  - Design target: re-audit `resource_limit_failure` after implementation and record final validation.
  - Evidence: `docs/pr17_failure_transition_matrix.md` now records the executable split planner, split lineage persistence, split-child resume semantics, and bounded replan fallback. Final validation on Monday, August 31, 2026 passed for the implementation commit.
  - Tests: Focused post-refactor execution passed: `92 passed, 8521 warnings in 1.29s`. Final validation passed: coding-principles gate 0; mypy `Success: no issues found in 13 source files`; full suite `259 passed, 27456 warnings in 11.92s`; `compileall` passed; `git diff --check` passed.
  - Commit SHA: `54efdde`

## Baseline findings

- `resource_limit_failure` currently produces `split_packet` but runtime still stops at `split_required`.
- `WorkPacketSplit`, `FailureProgressState.splits`, and `split_children` are persisted but not consumed by the coordinator.
- No current split planner exists.
- No current child scheduling or resume path exists for split work.
- Focused baseline before Phase 2 edits: `87 passed, 8054 warnings in 1.21s` for `tests/development/test_failure_progression.py` and `tests/development/test_behavior_contract_coordinator.py`.

INCOMPLETE_ITEMS = NONE
