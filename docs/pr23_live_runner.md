# PR23 live runner

The runner accepts `start` and `resume` with a run/project id, exactly one
requirement source, Python/pytest paths, state/evidence roots, and an optional
typed checkpoint. It delegates all lifecycle rules to `StrictTddRunController`.

`StrictTddLiveRunCompositionFactory` wires the existing feature composition,
repositories, lifecycle evidence, report writer, real-compatible local-primary
reasoning adapter, and Rack AI CLI gateway. Its injected gateway seams make
deterministic tests possible without live calls.

Exit codes: 0 success/checkpoint, 2 blocked, 3 stalled, 4 limit, 5 recovery-required, 6 input/configuration, and 7 receipt-delivery failure. Stdout is one JSON summary; credentials never enter state, events, reports, or stdout.


## Session 8B3C2B: deterministic failure and recovery contract

The deterministic executable happy path starts a durable run, emits one typed
transition at a time, honors an explicit checkpoint, reconstructs a fresh
composition on resume, completes, and regenerates its proof report from durable
state. A completed replay performs no new application, reasoning, or Rack AI
work.

A receipt is persisted before its projected lifecycle event is delivered. If
delivery fails after the event was durably appended, the CLI exits 7 with
`receipt_delivery_failed`; the pending receipt remains in run state and a
report is written. A fresh CLI resume redelivers that receipt before advancing
the application. The deterministic lifecycle event id and existing sequence
are reused, so rematerialisation time cannot create a duplicate or sequence
conflict.

The residual crash window is an in-flight marker with no receipt: the
application may have returned but no durable receipt exists. This is
fail-closed. Resume writes a report, returns `recovery_required` (exit 5),
does not invent a projected event, and never retries the application
transition. Operator recovery is required.

Input/configuration errors are rejected before run state is created. Terminal
blocked and invocation-limit outcomes also write reports. Focused proof guards
fail immediately if a real Rack AI CLI gateway, local-primary HTTP path, or
network socket is contacted. The runner itself has no direct subprocess, Git,
regression, microcycle, scenario, behavior-repair, or Rack AI work-unit logic.


## Checkpoint/resume non-repetition correction

A checkpoint after canonical promotion persists the microcycle's next action. Resume
continues from that durable state; it does not repeat the completed frontier's
Developer attempt, deterministic regression, canonical promotion, or Rack AI
work-unit identity. The executable proof compares the checkpoint frontier's
persisted developer attempts and frontier attempt counts with the resumed
state, and rejects repeat work-unit IDs or matching lifecycle
kind/candidate-revision facts.

Receipt redelivery is deliberately different: it may rematerialise the one
pending lifecycle event with the same deterministic event ID and sequence
before any application advance. It never reruns the application transition
that produced the receipt. Subsequent application work, if required, is a
new frontier transition.
