# PR30 Naming Assessor prompt correction

Starting branch: design/post-behavior-naming-refactoring.
Starting SHA: 1e829eab183616927c32df73d7b2c4c0431aa1b9.

The Naming Assessor question now defines a mismatch only when an explicitly
required identifier is absent and the same public/product concept exists under
another identifier. A required identifier already present requires NO. The prompt
excludes alias/duplicate-helper removal, syntax and API-shape changes, style,
cleanup and refactoring. Its exact-identifier output examples have no trailing
punctuation and it explicitly forbids additional output.

Only NAMING_INSTRUCTION changed in application code. An AST comparison confirms
all remaining application code in its module is identical. Parser tolerance,
authority, retries, focused material, Renamer, Refactor Assessor/Refactorer,
Gatekeeper, behavioral TDD and post-behavior state machinery are unchanged.

Six focused cases were added in test_post_behavior_boundaries.py. They inspect
the actual outgoing model prompt, preserve the one-call NO path, and demonstrate
that a valid get_total -> total mapping parses while punctuation suffixes remain
invalid. No existing test was removed or weakened.

The first shell test command failed before collection because DJANGO_SECRET_KEY
was absent. It is retained in naming-focused.log. Deterministic validation uses
the same explicit environment as the previous PR30 validation. This is an
operator environment correction, not an application change.

The live requirement is unchanged:
docs/evidence/pr30-20260910/live-requirement.txt
SHA256: f94d99e83d826442c4d70d581dd46e91ebf1dc0e580eb3182f38a5c9d02e1f78.
The proof uses the existing runner and local-primary at http://127.0.0.1:8017/v1,
with fresh run/project identities and no manual edits to generated artifacts.
A naming NO is allowed to proceed into ordinary refactoring. Lifecycle completion
and the runner's stricter positive rename/refactor-chain qualification are
reported separately.

## Deterministic validation

Implementation SHA: f4b491fb2bb92f6a1865c29fd763d2c42b49e823.

- Naming/post-behavior boundaries and material: 59 passed.
- Existing PR30 suite, including six added cases: 175 passed.
- Full ATHBA pytest: 1,200 passed in 631.00 seconds.
- Coding-principles gate: passed.
- Configured mypy: passed, 57 source files.
- Compileall: passed (core, athba, llm_service, scripts).
- git diff --check: passed.

Exact commands, timings, exit codes and log hashes are in validation.json.
The logs retain existing deprecation warnings; no warning suppression was added.

## Exact new runtime instruction

```text
Compare the explicitly required identifier names with the production code. A naming mismatch exists only when an explicitly required identifier is absent and the same public/product concept is implemented under a different identifier. If the required identifier already exists in production, answer NO. Do not suggest removal of aliases or duplicate helpers, syntax changes, API-shape changes, style improvements, general cleanup or refactoring. Return exactly either: NO or: YES\ncurrent_name: <exact existing identifier>\nrequired_name: <exact required identifier> Do not add punctuation, explanation, markdown, or any other text.
```

The literal backslash-n output separators match the existing prompt convention.
No parser or response normalization was introduced.

## Fresh live result: blocked before Naming

Run/project: pr30-naming-prompt-20260911T082810Z.
The 45-second zero-retry local Responses readiness probe returned READY.
The unchanged proof runner exited 2 after 850.785 seconds.
Four behaviors completed over 139 application transitions. Final Specification
Gatekeeper reconciliation returned YES for six of seven checklist items.

REQ-004 (Calling total() returns the current total without changing it) returned
NO for every accepted test. Generated production has a total data attribute and
a value() accessor; the tests call value(). The persisted Gatekeeper rationales
say the evidence does not verify the required total() call and non-mutation.
The attempted split then failed its existing provenance validation:

- blocked_reason: specification_gatekeeper_unsplittable
- rejection_reason: invalid_split_response
- split_rationale: specification checklist provenance is not grounded in original source
- terminal run reason: specification_gatekeeper_failed

The complete raw attempted split and per-test judgments are in
gatekeeper-blocker.json. This is the observed upstream blocker, not a finding
that the corrected Naming prompt passed or failed. No additional model call,
workaround, fixture change or restart was made after this result.

Naming Assessor did not run: there is no raw Naming response for this fresh run.
Naming did not complete. Renamer, Refactor Assessor and Refactorer did not run.
POST_BEHAVIOR_COMPLETE was not reached. No post-behavior state was created.
The hypothesis about the Naming prompt remains untested by this live run.

Final canonical target: b9e6643daa95c3a6eb9327cc295bbc05010e09b6.
The target working tree and index are clean. This target is not a final
Gatekeeper-approved behavioral baseline; the proof report correctly has no
behavioral baseline or final accepted proof revision.

## Preservation

runtime-state.tar.gz contains 29 exact runtime, referenced packet, proof and
target snapshots, with hashes verified against runtime-state-manifest.json.
The target Git bundle was verified and retains all target refs. Readable target
snapshots use JSON-escaped source strings, retaining exact whitespace without
entering repository pytest collection or violating diff whitespace checks.
Final run and feature state are also retained separately. All 134 tracked
historical evidence files still match their pre-proof hashes, and the original
requirement bytes are unchanged. Existing unrelated untracked evidence is left
unstaged. No Rack AI source or configuration was changed.

The implementation changes two files:
core/development/post_behavior_assessment.py and
tests/development/test_post_behavior_boundaries.py.
The separate evidence commit adds only this directory; file-manifest.txt lists
its full contents. Existing PR30 is updated in place, with no merge.
