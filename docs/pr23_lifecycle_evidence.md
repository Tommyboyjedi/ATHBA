# PR23 lifecycle evidence

Session 8B3A adds a passive, typed lifecycle-evidence boundary. `StrictTddLifecycleEvent` uses typed event kinds and statuses, UTC timestamps, ordered identities, SHA/ref pairing, scenario/frontier consistency, and non-empty evidence references. The run context records the requirement and supplied ATHBA/Rack AI versions, rejecting secret-like values.

`StrictTddLifecycleEventRepository` stores one SHA-addressed directory per run with immutable metadata and an `events.jsonl` stream. It uses a single-host advisory lock and atomic rewrite; records are consecutive from zero, malformed or truncated streams fail closed, equivalent duplicate ids are idempotent, and conflicting ids or sequence numbers fail.

`NoOpStrictTddLifecycleEventSink` is the injection default. `PersistingStrictTddLifecycleEventSink` uses the explicit run context and repository sequence to persist an event without making domain services depend on a filesystem.

`StrictTddProofReportBuilder` only projects supplied persisted feature, scenario/microcycle, revision, and lifecycle-event state to deterministic structured data and Markdown. Missing evidence is rendered as `unavailable/incomplete`; it performs no model call, test execution, Git operation, or progression decision. Secret-like strings are redacted from report output.

The boundary is intentionally not wired to a CLI or live runner in 8B3A.
