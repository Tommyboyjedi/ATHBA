# PR30 evidence

Implementation revision: 32dfe17d4969927a784305d2892f63b927e76f35.

## Final deterministic validation

The source hashes in final-validation/validation.json bind the complete tested
implementation. All sources remained unchanged after validation and the interrupted
live attempt.

- Focused PR30 tests: **167 passed**.
- Complete ATHBA pytest suite: **1,061 passed** in 617.20 seconds.
- Coding-principles gate: **PASS**.
- Configured mypy: **PASS**, 54 source files.
- Compileall: **PASS**.
- Git diff whitespace checks: **PASS**, including staged new source files.

The complete suite used the immutable implementation revision above. The manifest
retains each exact command, exit code, duration and source hash. The full suite
reported 95,919 warnings; no tests failed.

## Live proof: stopped at the user's request

The local Responses readiness probe returned READY in 0.099 seconds. The fresh
disposable run pr30-live-running-total-20260910 then began. At
2026-09-10T09:30:26Z the user requested stopping the proof and taking it over manually.
The runner was terminated and its process exit was confirmed (SIGTERM, exit -15).
No further proof execution or model calls were performed.

The interruption occurred during existing behavioral planning, with
gatekeeper_checklist pending, two transitions completed and transition three in
flight. No Gatekeeper-approved behavioral baseline had been established, and the
post-behavior lifecycle had not started. The target setup SHA is
92aa8b6a8e39a1ea0f8f0d0090c5f880cecc5f91; this is **not** a behavioral acceptance SHA.
No manual target-code edits were made.

Live proof is **incomplete / deferred to the user**, not PASS and not an
infrastructure failure. The preserved runtime record still says running because
it records the interruption; it was not rewritten to manufacture a terminal result.
Use a fresh disposable project/run identity for a manual proof. The interrupted
run is retained as evidence and has not been resumed.

The live-plan.json, live-requirement.txt, readiness request/result, shell invocation,
cancellation receipt and immutable predeclaration preserve what was attempted.
The interrupted-state/ directory holds the exact run/feature/project/lifecycle-event
records and a Git bundle of the disposable target. The interrupted-state-summary.json
binds the snapshot hashes. Original runtime state remains in /srv/ATHBA/state.

## Earlier validation history

Logs and validation.json immediately in this directory preserve an earlier run
(148 focused / 1,042 full tests passed). Generic cross-module rename and public
interface preservation tests were added after that run began. That record remains
history and is superseded by final-validation/.

The historical top-level evidence/ directory is untouched and excluded from
these changes.
