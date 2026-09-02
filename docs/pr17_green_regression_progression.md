# PR17 Green Regression Progression

## Purpose

PR17 keeps the ordinary Developer narrowly scoped to one accepted RED behavior. ATHBA owns global compatibility checks after that narrow GREEN succeeds.

Progression is:

1. Tester creates one RED candidate.
2. RED verification proves the candidate is trustworthy.
3. Developer makes only that one accepted RED test pass.
4. ATHBA runs an independent regression gate across all accepted GREEN tests plus the current target test.
5. If the gate is clear, the candidate may become the next development base and proceed to semantic review.
6. If the gate detects accumulated regression, ATHBA creates a bounded regression repair work unit.
7. After any regression repair or semantic review repair succeeds locally, ATHBA reruns the full regression gate before promotion or semantic approval.

## Narrow Developer Contract

The ordinary Developer work unit proves only the current accepted RED test is GREEN.

It must:

- work only in the selected production file;
- make the specified accepted test pass;
- make the smallest coherent production change necessary;
- avoid unrelated behavior, extra tests, extra files, extra dependencies, speculative abstractions, and future requirements.

The ordinary Developer prompt and acceptance contract must not ask the worker to make the full suite pass.

## Independent Full Regression Gate

ATHBA runs the regression gate after Developer success. The gate is deterministic supervisory work, not Developer reasoning.

The gate persists typed evidence:

- candidate revision;
- target test node;
- accepted regression suite members;
- target result;
- full-suite result;
- exact failing prior test nodes;
- passing prior test nodes when needed;
- stdout/stderr;
- evidence references;
- regression disposition.

Current dispositions are:

- `regression_clear`
- `accumulated_regression`
- `regression_infrastructure_failure`

`development_base_revision` advances only after target GREEN and `regression_clear`.

## Accepted GREEN Authority

ATHBA persists `accepted_green_test_names` as the authoritative accepted regression set. The regression suite always includes:

- all previously accepted GREEN tests;
- the current target test.

A test remains regression authority once it is GREEN, even if its semantic review is provisional and still carries open obligations.

## Accumulated Regression and Bounded Repair

If the current target test passes but previously accepted tests fail, ATHBA records `accumulated_regression` and moves to bounded regression repair.

The regression repair packet includes only the conflict set:

- the new target test, because it must stay GREEN;
- the previously accepted failing tests, because they must be restored.

Passing unrelated tests are not placed into the repair packet. Local repair acceptance may check only the conflict set, but that is not final promotion. ATHBA reruns the full regression gate after each accepted repair.

## Promotion, Persistence, and Resume

Promotion and Developer success are separate events.

Persisted state includes:

- `development_base_revision` before promotion;
- current candidate revision;
- accepted GREEN authority;
- latest regression gate result;
- failing regression nodes;
- semantic review result when present;
- semantic repair attempts;
- regression repair attempts.

Resume behavior must preserve discovered regressions. If a run resumes from `repair_ready` with an accumulated regression result, ATHBA continues from bounded regression repair rather than rerunning the original RED or Developer packet.
