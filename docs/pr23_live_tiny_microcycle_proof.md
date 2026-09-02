# PR23 revised live tiny microcycle proof

Date: 2026-09-01

Status: FAIL -- bounded model-capability blocker during real Tester scenario drafting.

> **Session 8C1 review note:** The historical four-attempt failure remains
> factual, but the blanket MODEL_CAPABILITY_BLOCKER classification was
> premature. Later architectural review found that attempts one and two were
> partly rejected by ATHBA-owned source-metadata and exact-identity
> requirements, while attempts three and four had distinct scenario defects.
> See [PR23 scenario submission contract review](pr23_scenario_submission_contract_review.md).
> This note does not change the recorded live outcome or authorize another run.


## Scope and preconditions

- ATHBA branch: `pr23-strict-tdd-microcycle-implementation` at `c9c30a0355b2389e21ac94e746325ce9600c2b89`.
- Rack AI: `a3ed3195f40e40168116763ac2ed1bf55ed3f494`; its trusted ATHBA project/runtime roots were verified. Rack AI source and configuration were not modified.
- Protected legacy: `8334f42a8865b9360972f5e0422a8f61d02dedb6`, unchanged.
- The ATHBA branch was clean and synchronized with origin before the final project was created.
- The runner used real `local-primary` reasoning through the local OpenAI-compatible Responses endpoint and real Rack AI CLI work units. The local endpoint was given the non-secret `local-primary` bearer label required by ATHBA's provider configuration.
- ReservationBook and PR21 were not run or implemented.

## Generic corrections before the final fresh project

Three generic defects were discovered and corrected with requirement-neutral regression coverage before the final proof run:

1. `40539e0` seeds caller-declared production paths as comment-only modules in the generated repository, so a live project can meet the empty-module precondition without manual target-repository edits. Full required suite: `447 passed`.
2. `ce48406` resolves ATHBA's version from the configured ATHBA checkout rather than a not-yet-created disposable project repository. Focused runner/controller/environment suite: `19 passed`.
3. `c9c30a0` submits the next bounded Tester attempt after an invalid scenario candidate instead of re-reviewing the same invalid candidate. Focused scenario suite: `9 passed`.

The project `pr23-live-toggle-switch-20260901T210000Z` was contaminated by item 3 after it reached real scenario drafting and was not resumed. The final project below was newly created after the corrective commit was pushed and the branch was clean.

## Final fresh project

- Run/project id: `pr23-live-toggle-switch-20260901T210938Z`.
- Project path: `/srv/ATHBA/state/projects/pr23-live-toggle-switch-20260901T210938Z/repository`.
- Initial canonical development base: `a2691b97d09d967d9cd51a8bb17704c8729eadfc`.
- Managed working ref: none created; no approved scenario reached microcycles.
- Production path: `toggle_switch.py`; it was committed before any model call as the comment-only module `"""ATHBA initial production module."""`.
- Test path: `tests/test_toggle_switch.py`.
- Exact persisted source requirement before planning:

> Build a small in-memory ToggleSwitch. It can be instantiated, begins in the off state, and calling toggle changes it to the on state.

## Real execution evidence

The real Behavior Planner produced a three-item contract (instantiate, observe off state, toggle on); the real independent Gatekeeper produced the corresponding checklist. Rack AI then executed four distinct Tester work units for the first behavior (`REQ-001`), each on the same trusted base with distinct change and work-unit identities.

| Attempt | Change id suffix | Rack AI result | ATHBA outcome |
| --- | --- | --- | --- |
| 1 | `scenario-draft-1--attempt-1` | `checks_passed`, `approved` | candidate invalid: required scenario rationale/source-reference metadata not accepted |
| 2 | `scenario-draft-2--attempt-2` | `checks_passed`, `approved` | candidate invalid: required scenario rationale/source-reference metadata not accepted |
| 3 | `scenario-draft-3--attempt-3` | `checks_passed`, `approved` | candidate invalid: required scenario rationale/source-reference metadata not accepted |
| 4 | `scenario-draft-4--attempt-4` | `checks_passed`, `approved` | persisted cap exhausted |

The preserved Rack AI packets are under `/srv/rack-ai/state/changes/pr23-live-toggle-switch-20260901T210938Z--REQ-001--scenario-draft-*-attempt-*/review-packet.json`. The ATHBA proof report is at `state/evidence/pr23-live-toggle-switch-20260901T210938Z/proof-report.md`.

The candidates demonstrate a model-quality limitation, not an ATHBA/Rack AI execution failure: one placed the required metadata inside a docstring rather than the supported scenario form, another changed the canonical identity shape, another skipped the missing import and introduced extra assumptions, and the final candidate substituted a mock class for the required production type. Rack AI correctly returned accepted candidate revisions under its bounded execution contract; ATHBA correctly rejected them at its independent scenario boundary.

No prompt was manually tuned, no fake gateway was introduced, and no unchanged task exceeded four attempts. The run stopped fail-closed with `attempts_exhausted` before an approved complete scenario, strict frontier, Developer work unit, deterministic regression, resume checkpoint, Senior behavior review, or final reconciliation.

## Deferred observations

Because Tester could not produce an approved scenario, the following are not demonstrated by this live run: missing-type RED, missing-operation RED, behavioral-assertion RED, Developer minimum change/frontier visibility, deterministic per-GREEN regression, canonical final test, process restart/resume, Senior review/repair, and final Gatekeeper reconciliation. The final target repository remains at its initial seed revision and contains no Developer changes.

PR23_LIVE_TINY_PROOF = FAIL
REAL_REASONING_USED = YES
REAL_RACK_AI_USED = YES
MISSING_TYPE_FRONTIER_RED = FAIL
MISSING_OPERATION_FRONTIER_RED = FAIL
BEHAVIORAL_FRONTIER_RED = FAIL
DEVELOPER_MINIMUM_CHANGE = FAIL
DEVELOPER_SEES_ONLY_FRONTIER = NO
DETERMINISTIC_REGRESSION = FAIL
REGRESSION_REASONING_CALLS = ZERO
ONE_CANONICAL_TEST = NO
LIVE_RESUME = FAIL
BEHAVIOR_REVIEW_END_TO_END = FAIL
BEHAVIOR_REPAIR_END_TO_END = NOT_USED
FINAL_RECONCILIATION = FAIL
UNCHANGED_TASK_ATTEMPTS_OVER_FOUR = NO
MODEL_CAPABILITY_BLOCKER = YES
GENERIC_ATHBA_DEFECT_FOUND = YES
PROOF_CONTAMINATED = NO
RESERVATIONBOOK_PROOF_STARTED = NO
RACK_AI_REPO_UNTOUCHED = YES
INCOMPLETE_ITEMS = PRESENT
LEGACY_BRANCH_UNCHANGED = YES
