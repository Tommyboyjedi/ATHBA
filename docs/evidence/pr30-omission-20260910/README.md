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
   unless and otherwise. Final punctuation may be quoted but never crossed.
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
the corresponding logs. The 69 new tests cover exact and omitted quotes, recorded
live outputs, order, overlap, missing/paraphrased text, malformed markers, clause
boundaries, subject grounding, modality, existing repair bounds and split behavior.

The fresh proof uses the original
docs/evidence/pr30-20260910/live-requirement.txt with a new identity, without target
or checklist edits. Its frozen plan, invocation, state and terminal outcome are
retained alongside this record. Any subsequent genuine blocker is preserved
without adapting the fixture or changing another lifecycle boundary.
