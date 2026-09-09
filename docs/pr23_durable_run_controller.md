# PR23 Durable Run Controller

## Purpose

`StrictTddRunController` is the outer durable controller for the existing one-transition feature application. It owns run identity, start/resume validation, invocation bounds, receipt delivery, lifecycle append, checkpoint and terminal stopping, stall detection, and proof reports. It does not select behaviors, route scenarios or microcycles, invoke Git, run regression, invoke Rack AI, or call live reasoning services.

## Typed run domain

`StrictTddRunRequest` contains the run and project identities, immutable feature request values, isolated state/evidence roots, mode, requested typed checkpoint, revisions, and `StrictTddRunControllerConfig`. Its immutable hash contains only project, requirement, language, framework, production paths, and test paths. Resume rejects a different hash.

`StrictTddRunState` is the only authoritative controller state document. It is schema-versioned, atomically persisted by `StrictTddRunStateRepository`, restores typed enums, rejects malformed values, and uses a validated run-id-derived path. It never persists credentials or an environment dump.

## Start and resume

Start rejects a pre-existing run or incompatible feature state, saves the initial run state, appends `run_started`, then may make one application advance. Resume requires matching persisted identity, appends one `run_resumed` event for the invocation, delivers a pending receipt first, and never re-advances a completed, blocked, stalled, or recovery-required run. A checkpointed state is eligible to continue on its next transition.

## Receipt delivery and failure boundary

Before application advancement, the controller saves an in-flight marker. After the one `application.advance()` call returns, it converts the typed result to `StrictTddTransitionReceipt` and persists that receipt before projecting or appending an event. A replay projects the same typed path, stable fingerprint, and occurrence, therefore keeps the same event identity and does not call the application again.

If append fails, the receipt remains pending and a resume retries it. If saving final controller state fails after append, the persisted receipt remains available for idempotent replay. An in-flight marker without a receipt is an unavoidable non-transactional interruption boundary: it fails closed as `transition_receipt_recovery_required`; no status text is used to fabricate an application result.

## Lifecycle ownership and policies

The application projector emits application events such as `feature_completed`, `feature_blocked`, and `transition_blocked`; it never emits run terminal events. The controller emits `run_started`, `run_resumed`, `controlled_checkpoint_stop`, `run_blocked`, and `run_completed`, after the application transition event that caused stopping.

Checkpoint matching delegates solely to `StrictTddCheckpointPolicy`. Terminal matching delegates to `StrictTddTerminalPolicy`; no-transition/no-checkpoint is a typed blocked outcome, never an unnamed `checkpoint=None`. Equal stable fingerprint and path are marked stalled; retry-count changes and a new frontier remain progress. The separate `run()` loop is bounded by the typed invocation configuration.

## Reports

`StrictTddRunEvidenceSnapshotCollector` loads only the feature-owned current, pending, completed, and receipt scenario identities. It gathers the corresponding scenario draft, microcycle, revision, and lifecycle state without scanning global directories. `StrictTddRunReportWriter` emits deterministic JSON and Markdown reports from that persisted evidence on checkpoint, block, complete, stall, transition-limit, and recovery returns. Missing evidence remains explicitly incomplete.

## Remaining scope

This layer has no CLI, environment-driven live composition, endpoint health probe, live tiny-feature proof, or ReservationBook proof. Those remain deliberately deferred.