# Deterministic bounded-omission provenance

The user-run PR30 proof pr30-live-running-total-20260910-100901 reached the
independent checklist atomizer on ATHBA 1ed201ca38723e10df553adb16c522efabd0ddf8.
Both retained attempts separated dependency-free and in-memory constraints, but
quoted the second obligation as:

> Keep the implementation ... in memory.

The unchanged original requirement ends:

> Keep the implementation dependency-free and in memory.

The previous literal-substring validator rejected both attempts solely because
the three-dot marker was not a literal substring. The original feature and proof
records are copied under exposed-failure/; their runtime originals are untouched.
The regression fixture preserves both raw responses. baseline-replay.json records
the old two-attempt failure and new single-attempt acceptance using deterministic
recorded responses, without any live model call.

## Rule and trust boundary

The existing exact contiguous-substring path, case-sensitive source comparison,
case-insensitive subject comparison and original modality-context extraction remain
unchanged.

Only if exact lookup fails may three ASCII dots act as an omission marker:

1. Split at every marker. Each segment must contain a word character. Empty,
   leading, trailing, consecutive and punctuation-only segments are rejected.
   Four-or-more-dot runs and Unicode ellipsis are not alternate markers.
2. Trim spaces/tabs immediately beside markers. All characters inside every
   segment must otherwise match the source verbatim, with case and punctuation
   preserved. No general whitespace, spelling or Unicode normalization is used.
3. Find every segment in order inside one source unit, searching forward from the
   previous segment's end. Matches cannot overlap or reuse earlier text. Word
   boundaries prevent fragments of separate words from forming apparent words.
4. Units are conservatively delimited by period, exclamation mark, question mark,
   semicolon, colon, comma, CR/LF, Unicode line/paragraph separators, en/em dashes,
   and the explicit clause separators but, whereas, although, while, however,
   unless and otherwise. Coordinating and/or/nor also delimit a unit when they
   introduce an explicit new subject determiner/pronoun or a finite/modal
   predicate after an already stated predicate/operator or imperative prefix.
   Coordinated subjects before a shared predicate stay together. Shared adjectival or prepositional conjunctions remain possible.
   Final punctuation may be quoted but never crossed.
   Ambiguous punctuation therefore causes rejection on the omission path;
   a full exact quote remains available.
5. The subject must occur entirely inside one retained segment. It cannot bridge
   an omission or name text present only in the omitted gap.
6. The unchanged grounded_modality validator receives the original complete source
   unit, including omitted words. Omitting must not, optional or not required
   cannot conceal a contradictory modality.

This is deterministic textual provenance, not semantic equivalence. The helper
returns a typed provenance value. It does not rewrite the stored quote, invent
source text, perform fuzzy matching or call a model. The existing initial request
plus at most one repair uses the same validator. Checklist splitting also reuses
that validator. The existing contiguous-modality prompt rule remains in place;
the shared schema/rules now describe the additional bounded quote form.

Only atomization provenance and its source schema/rules changed. Behavior planning,
TDD, final reconciliation, PR30 naming/refactoring, and Rack AI are unchanged.

## Validation and fresh live proof

Exact commands, source identities and results are retained in validation.json and
the corresponding logs. The 75 new tests cover exact and omitted quotes, recorded
live outputs, order, overlap, missing/paraphrased text, malformed markers, clause
boundaries, subject grounding, modality, existing repair bounds and split behavior.

The fresh proof uses the original
docs/evidence/pr30-20260910/live-requirement.txt with a new identity, without target
or checklist edits. Its frozen plan, invocation, state and terminal outcome are
retained alongside this record. Any subsequent genuine blocker is preserved
without adapting the fixture or changing another lifecycle boundary.

## Final results

Implementation commits are a107c7ac76255a1246164c26fa0d199855280778 and
175ff8f69bc1857b449ae3a1051f77d5141fa988. Final validation and the fresh live proof
used the latter exact revision; its source hashes remained unchanged.

| Check | Result |
| --- | --- |
| Focused specification/Gatekeeper tests | 202 passed |
| PR30 focused tests | 167 passed |
| Complete ATHBA pytest suite | 1,136 passed in 619.23 seconds |
| Coding-principles gate | PASS |
| Configured mypy | PASS, 55 source files |
| Compileall | PASS |
| Working and staged diff whitespace checks | PASS |

The earlier full run at a107c7a was intentionally stopped to add coordinated-clause
coverage. Its exit -15 is retained under superseded-validation/ and is not counted
as a successful full run. No existing tests were weakened or removed.

### Fresh live outcome: checklist creation PASS; full chain BLOCKED

Fresh identity: pr30-omission-running-total-20260910T114333Z.
Original requirement SHA256:
f94d99e83d826442c4d70d581dd46e91ebf1dc0e580eb3182f38a5c9d02e1f78.

The live atomizer returned seven items, including separate dependency-free and
in-memory obligations. It used the bounded quote
"Keep the implementation ... in memory", which passed in one attempt without
repair. The exact original requirement, generated checklist and target code were
not manually edited.

All four behaviors completed. After 137 transitions, final reconciliation returned
YES for pr30-001 through pr30-006, then NO for pr30-007:

- status/reason: specification_gatekeeper_failed;
- evidence policy/status: unsupported_evidence_policy;
- rationale: source provenance mismatch;
- source quote: Keep the implementation ... in memory.

The next blocker is the separate literal-substring guard in
core/development/specification_evidence_routing.py:45-49. It still rejects the
otherwise validated omission quote before evaluating the in-memory constraint.
Final reconciliation was explicitly out of scope and remains unchanged. This is
an ATHBA downstream provenance incompatibility, not a live infrastructure failure.
No fixture, model, generated checklist or harness was adapted after observing it.

Last canonical target revision:
8257a3c1ebec6bb492ff81e22b73bdc47c1b7bb1.
It is not a final Gatekeeper-approved behavioral baseline. Neither naming nor
refactoring started; POST_BEHAVIOR_COMPLETE and the full positive chain are not
claimed. The runner terminated normally with blocked status (exit 2), after
1,082.923 seconds. An earlier 300-second workspace timeout was recovered by the
existing bounded retry policy and is retained in the attempt evidence.

The live-result.json and final-feature-state.json identify the exact terminal
results. The live/ directory retains the immutable predeclaration and full
behavioral reports. runtime-state.tar.gz contains this run's durable state and
all referenced Rack review packets; runtime-state-manifest.json records their
original paths and SHA256 hashes. target-repository.bundle preserves all local
target refs and was verified with git bundle verify. Original runtime files and
the target repository remain intact under /srv/ATHBA/state.

The complete positive PR30 proof remains blocked on the downstream final
reconciliation provenance guard. The atomization correction is deterministically
green and directly demonstrated on the real local path.
