# TDD Progression Refactor Plan

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
Target module: `core/development/tdd_progression.py`

## Session checklist

- [x] Verify branch and protected historical snapshot.
  Evidence: `git rev-parse --abbrev-ref HEAD` returned `pr17-specification-gatekeeper`; `git rev-parse legacy` returned `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
  Commit SHA: `WORKTREE`
- [x] Inventory current module size and class list.
  Evidence: `wc -c core/development/tdd_progression.py` returned `49419`; classes currently defined are `TddPhase`, `TddBehavior`, `TddPhaseState`, `TddBehaviorProgress`, `SourceRequirementClause`, `SpecificationChecklistItem`, `SpecificationChecklist`, `ChecklistEvidence`, `SpecificationGap`, `ChecklistItemAssessment`, `GatekeeperAssessmentRecord`, `SpecificationGatekeeperRunState`, `BehaviorContractRequirement`, `BehaviorContract`, `TddStepProposal`, `TddStepDecision`, `SemanticReviewResult`, `ContractCycleRecord`, `BehaviorContractRunState`, and `TddSnapshot`.
  Commit SHA: `WORKTREE`
- [x] Read mandatory architecture and coding-principle inputs.
  Evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the GitHub PR17 description, `docs/pr17-specification-gatekeeper.md`, and the current `scripts/check_coding_principles.py`.
  Commit SHA: `WORKTREE`
- [x] Identify direct importers and focused tests before editing.
  Evidence: direct importers are `core/datastore/repos/tdd_state_repo.py`, `core/development/tdd_coordinator.py`, `core/development/behavior_contract_coordinator.py`, `core/development/specification_gatekeeper.py`, `core/development/test_evidence_reconciliation.py`, `core/development/contract_run_store.py`, `tests/development/test_tdd_coordinator.py`, `tests/development/test_behavior_contract_coordinator.py`, `tests/development/test_specification_gatekeeper.py`, and `tests/development/test_test_evidence_reconciliation.py`.
  Commit SHA: `WORKTREE`
- [x] Run focused baseline tests before refactor.
  Evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_behavior_contract_coordinator.py tests/development/test_specification_gatekeeper.py tests/development/test_test_evidence_reconciliation.py tests/development/test_tdd_coordinator.py` passed with `93 passed`.
  Commit SHA: `WORKTREE`
- [ ] Split `core/development/tdd_progression.py` into cohesive domain modules while preserving public import compatibility.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Extend `scripts/check_coding_principles.py` to cover all Session 1 changed/new application classes without broad exemptions.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Add or update compatibility coverage where persisted state behavior is not already explicit.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Run post-refactor focused tests.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Run full suite.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Run compileall.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Run `git diff --check`.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Confirm clean `legacy` snapshot and push all commits to PR17.
  Evidence: pending.
  Commit SHA: `PENDING`
- [ ] Finalize this ledger with `INCOMPLETE_ITEMS = NONE` only after every mandatory item is complete.
  Evidence: pending.
  Commit SHA: `PENDING`

## Current module responsibilities

- TDD phase and per-phase work-unit state.
- Simple TDD behavior description and behavior progress state.
- Source requirement clause and specification checklist domain objects.
- Gatekeeper evidence, item assessment, gap, and gatekeeper run state.
- Behavior Contract requirement and Behavior Contract domain objects.
- TDD step proposal/decision and semantic review result records.
- Contract-cycle and contract-run state.
- Repository snapshot serialization for TDD and Behavior Contract runs.
- Shared validation helpers, path/ref helpers, and evidence-kind normalization.

## Current class list by domain family

- TDD behavior and phase state: `TddPhase`, `TddBehavior`, `TddPhaseState`, `TddBehaviorProgress`.
- Specification source and checklist: `SourceRequirementClause`, `SpecificationChecklistItem`, `SpecificationChecklist`.
- Gatekeeper evidence and assessment: `ChecklistEvidence`, `SpecificationGap`, `ChecklistItemAssessment`, `GatekeeperAssessmentRecord`, `SpecificationGatekeeperRunState`.
- Behavior Contract domain: `BehaviorContractRequirement`, `BehaviorContract`.
- TDD cycle and review state: `TddStepProposal`, `TddStepDecision`, `SemanticReviewResult`, `ContractCycleRecord`, `BehaviorContractRunState`.
- Repository snapshot: `TddSnapshot`.

## Current coding-principle violations and risks

- `core/development/tdd_progression.py` mixes multiple unrelated domain families in one 49 KB module.
- Application-significant states are represented by raw module-level string sets such as contract pools, review verdicts, checklist kinds, evidence kinds, and assessment statuses.
- Validation and serialization helpers are shared across unrelated concepts, which hides domain boundaries.
- `BehaviorContract.from_dict` currently exposes boundary-specific allowed-path validation through a multi-input classmethod rather than a separate typed input object or codec.
- Persistence boundaries are repeated per class; compatibility is explicit but mechanically scattered.

## Persistence interfaces to preserve

- `TddPhaseState.to_dict` / `from_dict`
- `TddBehaviorProgress.to_dict` / `from_dict`
- `SourceRequirementClause.to_dict` / `from_dict`
- `SpecificationChecklistItem.to_dict` / `from_dict`
- `SpecificationChecklist.to_dict` / `from_dict`
- `ChecklistEvidence.to_dict` / `from_dict`
- `SpecificationGap.to_dict` / `from_dict`
- `ChecklistItemAssessment.to_dict` / `from_dict`
- `GatekeeperAssessmentRecord.to_dict` / `from_dict`
- `SpecificationGatekeeperRunState.to_dict` / `from_dict`
- `BehaviorContractRequirement.to_dict` / `from_dict`
- `BehaviorContract.to_dict` / `from_dict`
- `TddStepProposal.to_dict` / `from_dict`
- `TddStepDecision.to_dict` / `from_dict`
- `SemanticReviewResult.to_dict` / `from_dict`
- `ContractCycleRecord.to_dict` / `from_dict`
- `BehaviorContractRunState.to_dict` / `from_dict`
- `TddSnapshot.to_dict` / `from_dict`

## Focused tests and current evidence

- Behavior Contract serialization and validation: `tests/development/test_behavior_contract_coordinator.py`
- Gatekeeper checklist, evidence, gap, and assessment persistence: `tests/development/test_specification_gatekeeper.py`
- Final reconciliation behavior over accepted tests: `tests/development/test_test_evidence_reconciliation.py`
- TDD snapshot persistence and resume behavior: `tests/development/test_tdd_coordinator.py`
- Baseline result on 2026-08-30: `93 passed` for the focused four-file test set above.

## Planned target modules

- `core/development/tdd_progression.py`
  Responsibility: compatibility facade and small work-unit helper re-exports only.
- `core/development/tdd_domain.py`
  Responsibility: TDD phase enum, TDD behavior data, phase state, behavior progress, work-unit id helpers.
- `core/development/specification_domain.py`
  Responsibility: source clauses, checklist items, checklist container, evidence kind/checklist kind typed values, specification gaps, assessments, gatekeeper run state.
- `core/development/behavior_contract_domain.py`
  Responsibility: Behavior Contract requirement and contract domain model plus contract-specific validation and load options.
- `core/development/contract_run_domain.py`
  Responsibility: TDD step proposal/decision, semantic review result, cycle state, contract run state, snapshot state.
- `core/development/tdd_progression_validation.py`
  Responsibility: reusable validation and repository-relative path helpers shared by the domain modules without introducing a generic framework.

## Importing modules to preserve

- `core/datastore/repos/tdd_state_repo.py`
- `core/development/tdd_coordinator.py`
- `core/development/behavior_contract_coordinator.py`
- `core/development/specification_gatekeeper.py`
- `core/development/test_evidence_reconciliation.py`
- `core/development/contract_run_store.py`
- `tests/development/test_tdd_coordinator.py`
- `tests/development/test_behavior_contract_coordinator.py`
- `tests/development/test_specification_gatekeeper.py`
- `tests/development/test_test_evidence_reconciliation.py`

## Notes for the refactor

- Preserve persisted keys, optional/default behavior, and stable status-string values at the serialization boundary.
- Keep older payloads readable, including `quality` evidence-kind normalization behavior.
- Do not move ATHBA semantics into Rack AI or otherwise change repository boundaries.
- Prefer a compatibility facade over widespread importer churn.
- If a typed enum is introduced internally, serialize via stable `.value` strings.

INCOMPLETE_ITEMS = PRESENT
