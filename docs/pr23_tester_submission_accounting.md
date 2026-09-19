# PR23 Tester submission accounting

The fixed budget is four actual external Tester submissions, not four accepted revisions and not four retries plus an initial request. Attempt five is impossible.

The persisted attempt records now retain a typed mode and no-candidate outcome. Modes are fresh_draft, fresh_retry_after_no_candidate, repair_previous_candidate, and retry_repair_from_existing_candidate.

A selected-worker model failure with no candidate (disallowed/unknown tool, model timeout, protocol failure, or completed-without-candidate) consumes one submission. A fresh retry retains the canonical development base, exact terminal feedback, and no fabricated source/ref/SHA. Candidate-producing failures retain normal candidate repair lineage. An external blocker (no worker selected, executor/transport/provenance failure, malformed packet, advertised-tool-denied mismatch, or unknown origin) fails closed and consumes no further submission.

Deterministic coverage proves four selected local-coder no-candidate submissions are recorded with modes 1=fresh_draft, 2-4=fresh_retry_after_no_candidate, all bases canonical, and no fifth invocation. It also proves an unselected timeout fails closed without an attempt.
