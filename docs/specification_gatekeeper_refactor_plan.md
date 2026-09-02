# Specification Gatekeeper Refactor Plan

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Legacy snapshot: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
Target modules:
- `core/development/specification_gatekeeper.py`
- `core/development/test_evidence_reconciliation.py`

## Session checklist

- [x] Verify branch and protected historical snapshot.
  Target responsibility: branch safety and historical boundary preservation.
  Implementation evidence: `git rev-parse --abbrev-ref HEAD` returned `pr17-specification-gatekeeper`; `git rev-parse legacy` returned `8334f42a8865b9360972f5e0422a8f61d02dedb6`.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Read mandatory inputs before editing.
  Target responsibility: architectural and coding-principle compliance.
  Implementation evidence: reviewed `AGENTS.md`, `agent.MD`, `coding_principles.MD`, the current PR17 description, `docs/pr17-specification-gatekeeper.md`, `scripts/check_coding_principles.py`, `docs/tdd_progression_refactor_plan.md`, `docs/failure_progression_refactor_plan.md`, and the current gatekeeper/reconciliation tests and call sites.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Inventory current module sizes, classes/functions, reasoning calls, persistence surfaces, and public callers.
  Target responsibility: exact pre-refactor subsystem map.
  Implementation evidence: `specification_gatekeeper.py` is `18468` bytes / `404` lines; `test_evidence_reconciliation.py` is `7980` bytes / `211` lines. Public classes/functions are the current planner, gatekeeper, gap adapter, accepted-test catalog, reconciler, prompt builders, JSON parsing helpers, evidence collectors, and source-ref matching helpers. Public callers currently include `core/development/behavior_contract_coordinator.py`, `scripts/run_specification_gatekeeper_probe.py`, `scripts/run_pr17_independent_reservation_book.py`, `tests/development/test_specification_gatekeeper.py`, and `tests/development/test_test_evidence_reconciliation.py`.
  Tests: N/A.
  Commit SHA: `WORKTREE`
- [x] Identify focused baseline tests before refactor.
  Target responsibility: behavior-preserving validation map.
  Implementation evidence: focused coverage is concentrated in `tests/development/test_specification_gatekeeper.py`, `tests/development/test_test_evidence_reconciliation.py`, and gatekeeper integration paths in `tests/development/test_behavior_contract_coordinator.py`.
  Tests: planned baseline suite recorded below.
  Commit SHA: `WORKTREE`
- [x] Run focused baseline tests before refactor.
  Target responsibility: establish pre-change behavior baseline.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_specification_gatekeeper.py tests/development/test_test_evidence_reconciliation.py tests/development/test_behavior_contract_coordinator.py` passed with `80 passed`.
  Tests: `tests/development/test_specification_gatekeeper.py`, `tests/development/test_test_evidence_reconciliation.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `WORKTREE`
- [x] Decompose gatekeeper atomization, assessment, evidence collection, and gap adaptation into cohesive modules.
  Target responsibility: separate reasoning, deterministic evidence collection, gap adaptation, and compatibility facade.
  Implementation evidence: implementation moved into `core/development/specification_atomization.py`, `core/development/specification_assessment.py`, `core/development/specification_evidence.py`, and `core/development/specification_gap_adapter.py`; `core/development/specification_gatekeeper.py` is now a compatibility facade with re-exports only.
  Tests: focused gatekeeper/coordinator suite passed after the refactor.
  Commit SHA: `0968701`
- [x] Decompose accepted-test reconciliation into cohesive modules.
  Target responsibility: separate accepted-test discovery, final revision verification, YES/NO decision, and rendering/result types.
  Implementation evidence: implementation moved into `core/development/specification_reconciliation.py`; `core/development/test_evidence_reconciliation.py` is now a compatibility facade with re-exports only.
  Tests: focused reconciliation suite passed after the refactor.
  Commit SHA: `0968701`
- [x] Extend `scripts/check_coding_principles.py` to cover Session 3 changed/new application classes without broad exemptions.
  Target responsibility: machine enforcement for the refactor scope.
  Implementation evidence: the gate now includes `specification_atomization.py`, `specification_assessment.py`, `specification_evidence.py`, `specification_gap_adapter.py`, `specification_gatekeeper.py`, `specification_reconciliation.py`, and `test_evidence_reconciliation.py` alongside the Session 1 and Session 2 scope.
  Tests: `./.venv/bin/python scripts/check_coding_principles.py` returned `coding principles gate passed`.
  Commit SHA: `0968701`
- [x] Add or update compatibility coverage where state reload, independence, or final YES/NO proof integrity is not already explicit.
  Target responsibility: persistence and semantic safety.
  Implementation evidence: focused tests now explicitly prove atomization independence and rejection of stale accepted tests missing from the final trusted revision while preserving existing gatekeeper state round-trip coverage.
  Tests: `tests/development/test_specification_gatekeeper.py` and `tests/development/test_test_evidence_reconciliation.py` include the new coverage.
  Commit SHA: `0968701`
- [x] Run post-refactor focused tests.
  Target responsibility: prove local behavior preservation.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_specification_gatekeeper.py tests/development/test_test_evidence_reconciliation.py tests/development/test_behavior_contract_coordinator.py` passed with `82 passed`.
  Tests: `tests/development/test_specification_gatekeeper.py`, `tests/development/test_test_evidence_reconciliation.py`, `tests/development/test_behavior_contract_coordinator.py`.
  Commit SHA: `0968701`
- [x] Run full suite.
  Target responsibility: prove repository-wide compatibility.
  Implementation evidence: `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q` passed with `196 passed`.
  Tests: full ATHBA suite.
  Commit SHA: `0968701`
- [x] Run compileall.
  Target responsibility: import/compile integrity.
  Implementation evidence: `./.venv/bin/python -m compileall athba core llm_service tests scripts` completed without errors.
  Tests: `./.venv/bin/python -m compileall athba core llm_service tests scripts`.
  Commit SHA: `0968701`
- [x] Run `git diff --check`.
  Target responsibility: patch hygiene.
  Implementation evidence: `git diff --check` produced no output after the Session 3 refactor and ledger commits.
  Tests: `git diff --check`.
  Commit SHA: `468fee8`
- [x] Confirm `legacy` remains unchanged and push all commits to PR17.
  Target responsibility: branch integrity and final publication.
  Implementation evidence: `git rev-parse legacy` remained `8334f42a8865b9360972f5e0422a8f61d02dedb6`; `git push origin pr17-specification-gatekeeper` updated `origin/pr17-specification-gatekeeper` to `468fee8`.
  Tests: `git rev-parse legacy`, `git push origin pr17-specification-gatekeeper`.
  Commit SHA: `468fee8`
- [x] Finalize this ledger with `INCOMPLETE_ITEMS = NONE` only after every mandatory item is complete.
  Target responsibility: authoritative Session 3 record.
  Implementation evidence: this ledger now records the Session 3 module split, class audit, focused and full validation evidence, clean diff state, and branch push confirmation.
  Tests: N/A.
  Commit SHA: `c17e1c5`

## Current module sizes and structure

- `core/development/specification_gatekeeper.py`
  - Size: `18468` bytes
  - Lines: `404`
  - Classes: `SpecificationChecklistPlanner`, `SpecificationGapTddAdapter`, `SpecificationGatekeeper`
  - Module helpers: `_matching_contract_source_refs_for_item`, `_matching_contract_source_refs_for_gap`, `_matching_contract_source_refs_for_clause`, `_normalize_clause_text`, `_next_gap_requirement_ref`, `_json_object`, `_checklist_prompt`, `_assessment_evidence_kind`, `_evidence_mapping_prompt`
- `core/development/test_evidence_reconciliation.py`
  - Size: `7980` bytes
  - Lines: `211`
  - Classes: `AcceptedTestEvidence`, `ChecklistTestReconciliation`, `GitAcceptedTestCatalog`, `TestEvidenceReconciler`
  - Module helpers: `_accepted_tests`, `_reconciliation_prompt`, `_json_object`

## Current responsibility map

- `SpecificationChecklistPlanner`
  - Builds the independent atomization prompt.
  - Calls the reasoning gateway.
  - Parses checklist JSON into `SpecificationChecklist`.
- `SpecificationGapTddAdapter`
  - Turns one executable `SpecificationGap` into one supplemental `BehaviorContractRequirement`.
  - Resolves source traceability and stable generated refs.
- `SpecificationGatekeeper`
  - Creates initial run state when absent.
  - Assesses every checklist item.
  - Chooses evidence kind.
  - Builds and parses evidence-mapping reasoning requests.
  - Collects accepted test evidence candidates from TDD history.
  - Collects review evidence candidates from semantically approved cycles.
  - Creates `ChecklistItemAssessment`, `SpecificationGap`, and `GatekeeperAssessmentRecord` state.
- `GitAcceptedTestCatalog`
  - Reads final trusted test functions from git at a pinned semantic revision.
- `TestEvidenceReconciler`
  - Builds accepted-test candidate facts from run state.
  - Builds and parses reconciliation reasoning requests.
  - Applies deterministic final revision verification.
  - Enforces YES/NO result integrity.
- Helpers across both modules
  - JSON boundary parsing.
  - Prompt construction.
  - Contract/checklist source-ref matching.
  - Clause text normalization.

## Current reasoning boundaries

- Atomization reasoning call:
  - `SpecificationChecklistPlanner.create_checklist(...)`
  - Purpose: `athba_specification_checklist`
  - Inputs: only `project_id` and original `requirement_text`
- Gatekeeper evidence-mapping reasoning call:
  - `SpecificationGatekeeper._assess_item(...)`
  - Purpose: `athba_checklist_evidence_mapping`
  - Inputs: one checklist item plus accepted test candidates
- Final reconciliation reasoning call:
  - `TestEvidenceReconciler._reconcile_item(...)`
  - Purpose: `athba_checklist_test_reconciliation`
  - Inputs: one checklist item plus accepted TDD tests

## Current persistence surfaces to preserve

- `SpecificationChecklist.to_dict` / `from_dict`
- `ChecklistEvidence.to_dict` / `from_dict`
- `SpecificationGap.to_dict` / `from_dict`
- `ChecklistItemAssessment.to_dict` / `from_dict`
- `GatekeeperAssessmentRecord.to_dict` / `from_dict`
- `SpecificationGatekeeperRunState.to_dict` / `from_dict`
- `BehaviorContractRunState.to_dict` / `from_dict` persistence of `gatekeeper_state`
- Reconciliation result dictionaries via `ChecklistTestReconciliation.to_dict`

## Public callers and imports

- `core/development/behavior_contract_coordinator.py`
  - Uses `SpecificationGatekeeper.ensure_state`, `SpecificationGatekeeper.assess`, and `SpecificationGapTddAdapter.extend_contract_for_gap`.
- `scripts/run_specification_gatekeeper_probe.py`
  - Imports `SpecificationChecklistPlanner` and `_checklist_prompt`.
- `scripts/run_pr17_independent_reservation_book.py`
  - Imports `SpecificationChecklistPlanner`, `_checklist_prompt`, `GitAcceptedTestCatalog`, and `TestEvidenceReconciler`.
- `tests/development/test_specification_gatekeeper.py`
  - Imports planner, gap adapter, gatekeeper, and specification-domain records.
- `tests/development/test_test_evidence_reconciliation.py`
  - Imports catalog and reconciler.

## Current final reconciliation behavior

- Accepted test candidates are derived only from cycles with accepted RED and semantically approved GREEN history.
- The reconciler asks only whether an accepted unit test proves one checklist item.
- A `YES` is downgraded to `NO` when no test names are provided.
- A `YES` is downgraded to `NO` when a named test is not present in accepted semantically approved history or not present in git at the final trusted revision.
- `NO` remains visible and carries no accepted test names.
- No production code, review evidence, or mechanical evidence is allowed to substitute for accepted unit-test proof in final reconciliation.

## Current coding-principle violations

- `SpecificationGatekeeper` is too large at `201` executable lines.
- `SpecificationGatekeeper.assess`, `_assess_item`, `_accepted_test_candidates`, and `_approved_review_candidates` exceed the two-input rule.
- `TestEvidenceReconciler._reconcile_item` exceeds the two-input rule.
- Prompt building, JSON parsing, deterministic evidence collection, reasoning invocation, and state mutation are mixed inside the same gatekeeper/reconciler classes.

## Focused baseline tests and evidence

- `tests/development/test_specification_gatekeeper.py`
  - Covers checklist creation, malformed checklist failure, checklist round trips, independence of item classes, accepted TDD/review evidence proof, invented evidence downgrade, gatekeeper state reload, source-ref drift handling, gap adaptation, coordinator blocking on unproven checklist items, targeted gap reentry, and untraceable executable gap blocking.
- `tests/development/test_test_evidence_reconciliation.py`
  - Covers YES only for accepted final test evidence, invented test rejection, and purity/one-result-per-item behavior.
- `tests/development/test_behavior_contract_coordinator.py`
  - Covers gatekeeper integration paths and persisted run-state behavior around checklist progression.
- Baseline result on 2026-08-30: `80 passed` for the focused suite above.

## Planned target modules

- `core/development/specification_gatekeeper.py`
  - Responsibility: compatibility facade and small public entrypoints only.
- `core/development/specification_atomization.py`
  - Responsibility: checklist prompt construction, reasoning request building, and checklist decoding.
- `core/development/specification_assessment.py`
  - Responsibility: checklist-item assessment orchestration and gatekeeper assessment record construction.
- `core/development/specification_evidence.py`
  - Responsibility: deterministic accepted-test and review evidence collection plus evidence-mapping request types.
- `core/development/specification_gap_adapter.py`
  - Responsibility: gap-to-contract adaptation and source-trace helpers.
- `core/development/specification_reconciliation.py`
  - Responsibility: final YES/NO reconciliation orchestration and typed request/result objects.
- `core/development/specification_reconciliation_report.py`
  - Responsibility: human-readable reconciliation formatting if extraction proves cohesive.
- `core/development/test_evidence_reconciliation.py`
  - Responsibility: compatibility facade and re-exports only.

## Resulting modules

- `core/development/specification_gatekeeper.py`
  - Responsibility: compatibility facade and re-exports for planner, gatekeeper, gap adapter, and typed request objects.
- `core/development/specification_atomization.py`
  - Responsibility: independent checklist atomization request type, prompt construction, reasoning request construction, and checklist decoding.
- `core/development/specification_evidence.py`
  - Responsibility: deterministic accepted-test and review evidence collection, evidence-kind selection, and narrow evidence-mapping reasoning.
- `core/development/specification_assessment.py`
  - Responsibility: gatekeeper state creation, typed assessment requests, checklist-item assessment orchestration, and assessment-record construction.
- `core/development/specification_gap_adapter.py`
  - Responsibility: gap-to-contract adaptation, source-trace matching, clause normalization, and stable supplemental requirement id generation.
- `core/development/specification_reconciliation.py`
  - Responsibility: accepted-test discovery, final trusted revision verification, checklist-item YES/NO reconciliation, and reconciliation result types.
- `core/development/test_evidence_reconciliation.py`
  - Responsibility: compatibility facade and re-exports for final reconciliation types and services.

## Post-refactor class audit

- `core/development/specification_atomization.py:ChecklistAtomizationRequest` — responsibility: atomization request; executable lines: `3`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_atomization.py:SpecificationChecklistPlanner` — responsibility: independent checklist creation; executable lines: `17`; constructor inputs: `1`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_gap_adapter.py:SpecificationGapTddAdapter` — responsibility: gap-to-contract adaptation; executable lines: `20`; constructor inputs: `0`; max method inputs: `2`; inheritance: `composition-only`.
- `core/development/specification_evidence.py:ChecklistEvidenceContext` — responsibility: checklist evidence collection context; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_evidence.py:EvidenceMappingRequest` — responsibility: evidence-mapping request; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_evidence.py:AcceptedTestEvidenceCollector` — responsibility: accepted-test candidate collection; executable lines: `31`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_evidence.py:ApprovedReviewEvidenceCollector` — responsibility: review-evidence collection; executable lines: `28`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_evidence.py:ChecklistEvidenceMapper` — responsibility: accepted-test evidence mapping; executable lines: `17`; constructor inputs: `1`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_assessment.py:GatekeeperStateRequest` — responsibility: gatekeeper state request; executable lines: `3`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_assessment.py:GatekeeperAssessmentRequest` — responsibility: gatekeeper assessment request; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_assessment.py:ChecklistAssessmentContext` — responsibility: checklist assessment context; executable lines: `4`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_assessment.py:ChecklistItemAssessor` — responsibility: one checklist-item assessment; executable lines: `19`; constructor inputs: `1`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_assessment.py:GatekeeperAssessmentRunner` — responsibility: full assessment snapshot construction; executable lines: `23`; constructor inputs: `1`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_assessment.py:SpecificationGatekeeper` — responsibility: gatekeeper state creation and assessment coordination; executable lines: `20`; constructor inputs: `2`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:AcceptedTestEvidence` — responsibility: accepted-test fact record; executable lines: `17`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:ChecklistTestReconciliation` — responsibility: final YES/NO result record; executable lines: `21`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:ChecklistReconciliationRequest` — responsibility: single checklist-item reconciliation request; executable lines: `5`; constructor inputs: `0`; max method inputs: `0`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:GitAcceptedTestCatalog` — responsibility: final revision test identity verification; executable lines: `35`; constructor inputs: `2`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:AcceptedTestEvidenceCollector` — responsibility: approved-cycle accepted-test discovery; executable lines: `21`; constructor inputs: `0`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:ChecklistItemReconciler` — responsibility: one checklist item YES/NO reconciliation; executable lines: `18`; constructor inputs: `2`; max method inputs: `1`; inheritance: `composition-only`.
- `core/development/specification_reconciliation.py:TestEvidenceReconciler` — responsibility: full checklist reconciliation orchestration; executable lines: `23`; constructor inputs: `2`; max method inputs: `2`; inheritance: `composition-only`.

## Reconciliation integrity proof

- Final YES/NO reconciliation still consults only accepted unit-test candidates derived from semantically approved TDD history.
- A `YES` still downgrades to `NO` when the reasoning result omits named tests.
- A `YES` still downgrades to `NO` when a named test is absent from accepted history or absent from git at the final trusted revision.
- No review, code inspection, or mechanical fallback evidence was added to final reconciliation.

## Independence integrity requirements to preserve

- The atomization prompt must continue to receive only the original requirement text and project id.
- No Behavior Contract, TDD cycle, review output, test results, or planner output may be injected into the initial atomization reasoning request.
- Checklist item atomization must remain implementation- and proof-strategy-independent.

## Gap adaptation integrity requirements to preserve

- Supplemental requirements must keep source traceability.
- Gap adaptation must remain observable-behavior oriented and avoid implementation instructions.
- Existing duplicate-suppression and generated-ref behavior must remain intact.
- Adding a gap requirement must not itself mark a checklist item proven.

## Known out-of-scope or residual issues

- Session 3 does not add new Gatekeeper stages or repair loops.
- Session 3 does not change final YES/NO semantics.
- Session 3 does not redesign broader coordinator progression outside what is required for compatibility with the refactor.

INCOMPLETE_ITEMS = NONE
