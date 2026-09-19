# HISTORICAL EVIDENCE NOTICE

> This document is retained historical evidence.
> Its progression model is superseded by PR22.
> It is not the current implementation contract.

# PR17 Final ReservationBook Proof 3

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Starting task head: `97024172993ad43d7c549dfafe2034ddeb61fb58`
Rack AI head verified untouched: `a3ed3195f40e40168116763ac2ed1bf55ed3f494`
Legacy head verified unchanged: `8334f42a8865b9360972f5e0422a8f61d02dedb6`

## Scope and constraints

- Worked only in `/srv/ATHBA`.
- Did not modify `/srv/rack-ai`.
- Used real reasoning through `local-primary` at `http://127.0.0.1:8017/v1`.
- Used real Rack AI execution through the ATHBA live proof harness.
- Did not manually edit any generated target repository.
- Did not merge PR17 and did not implement PR21 refactoring.

## Mandatory starting verification

- `git status --short --branch` at start: `pr17-specification-gatekeeper` tracking `origin/pr17-specification-gatekeeper`.
- `git rev-parse HEAD` at start: `97024172993ad43d7c549dfafe2034ddeb61fb58`
- `git rev-parse legacy`: `8334f42a8865b9360972f5e0422a8f61d02dedb6`
- `/srv/rack-ai` ancestry check passed for `a3ed3195f40e40168116763ac2ed1bf55ed3f494`.

## Generic ATHBA defects found and fixed

### 1. Dependency decision repair could accept empty prerequisite refs

Contaminated run:
- `pr17-reservation-book-final3-20260831T152009Z-b`

Observed failure:
- `accepted dependency decisions require prerequisites`

Fixes committed:
- `5488083682b8f87032d80efcb25560b6c9bd01d4` `development: repair dependency decision recovery`

Effect:
- Repair prompts and validation now reject `already_planned` / `add_prerequisite` decisions with empty `prerequisite_refs`.

### 2. Proof harness promoted trusted revision on mechanical acceptance before semantic approval

Contaminated run:
- `pr17-reservation-book-final3-20260831T152919Z-clean`

Observed failure:
- Resume hit `base sha does not match the registered repository baseline` after an invalid RED candidate had already advanced the persisted trusted base.

Fixes committed:
- `92ec6259d6a2365d38495829210911f6c5d2cff6` `development: defer proof trust promotion until semantic approval`

Effect:
- `scripts/run_pr17_independent_reservation_book.py` now records mechanical acceptances separately and promotes only `semantic_revision`.

### 3. Replanned RED attempts reused the same Rack AI change/worktree identity

Contaminated run:
- `pr17-reservation-book-final3-20260831T154828Z-posttrust`

Observed failure:
- Resume hit `worktree already exists` because ATHBA reproposed the same RED step with the original deterministic change id.

Fixes committed:
- `07bee72b7e99c66c4fab1806320be4d63568fc85` `development: scope replanned red attempts for rack ai`

Effect:
- Replanned RED submissions now get attempt-scoped change keys, avoiding Rack AI workspace collisions while preserving normal in-cycle retry behavior.

## Final fresh run after all known fixes

Fresh run id:
- `pr17-reservation-book-final3-20260831T160201Z-finalretry`

First live pass outcome:
- Used real reasoning and real Rack AI execution.
- RED candidate was mechanically accepted at `49dd69810b6bc71df8824d1e4af9445b22906b4d`.
- Two-layer RED analysis rejected it as `invalid_test` because pytest failed at collection:
  - `ImportError: cannot import name 'ReservationBook' from 'reservation_book'`
- Persisted trusted base remained pinned at `52596136e1b278967c5e00fc581ff103284594ab`.
- Result correctly deferred until prerequisite `REQ-006` was approved.

Resume outcome on the same persisted run:
- Resume reused the persisted project and did not repeat the old Rack AI workspace collision; the new RED attempt used `--retry-1` in the change id.
- RED was again mechanically accepted and again rejected by two-layer RED analysis for the same collection failure.
- Persisted trusted base remained pinned at `52596136e1b278967c5e00fc581ff103284594ab`.
- No semantic approval was reached.

Evidence of the remaining blocker:
- Despite the recorded blocker `test_collection_or_bootstrap_failure: deferred until REQ-006 is approved`, ATHBA resumed by re-proposing the duplicate-resource RED step instead of first obtaining semantic proof for prerequisite `REQ-006`.
- This prevents the proof from reaching the required first semantically approved behavior and therefore blocks the end-to-end persistence resume proof.

## Validation performed

Focused regression validation after defect 2:
- `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_live_proof_scripts.py tests/development/test_behavior_contract_coordinator.py -q`

Focused regression validation after defect 3:
- `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true MONGO_USER=test MONGO_PASS=test ./.venv/bin/python -m pytest -q tests/development/test_behavior_contract_coordinator.py tests/development/test_live_proof_scripts.py -q`

Not completed because the proof remained blocked before final integrated acceptance:
- `scripts/check_coding_principles.py`
- `mypy`
- full pytest suite
- `compileall`
- final reconciliation / senior review end-to-end acceptance

## Current conclusion

PR17 final integrated ReservationBook proof 3 is still blocked.

What is now proven:
- Generic dependency-decision repair is fixed.
- Trusted revision progression no longer advances on mechanically accepted but semantically rejected RED candidates.
- Resume no longer collides with stale Rack AI workspaces for replanned RED steps.
- The final fresh run used the real reasoning gateway, real Rack AI execution, and the two-layer RED analysis.
- Invalid RED candidates did not reach GREEN and did not advance the trusted base.

What remains unproven:
- First semantic approval checkpoint.
- Persistence resume after at least one semantically approved behavior.
- Full green validation, senior review, final reconciliation, and final integrated test gates.

The remaining blocker appears to be ATHBA prerequisite progression on resume for this targeted specification-gap path: the run records deferral until `REQ-006`, but the next cycle still re-targets duplicate resource-id RED instead of acquiring semantic proof for `REQ-006` first.
