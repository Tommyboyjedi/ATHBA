# PR23 application run controller

StrictTddRunController is the typed, resumable application-level boundary around the Session 8B2 feature service. The request contains run/project identity, source requirement, language/test paths, state/evidence roots, start/resume mode, an optional typed checkpoint, and ATHBA/Rack AI revision metadata; it deliberately contains no credentials.

Start rejects existing run or feature state. Resume requires compatible persisted run and feature state, including requirement identity. The controller delegates feature progression to the existing feature application; it does not reimplement planning, scenario, microcycle, retry, review, or reconciliation state machines.

Each invocation persists its outer transition count and refuses work after the configured bound. A repeated identical non-complete result becomes a stalled run. A proof checkpoint is accepted only when persisted application evidence supplies the matching marker. Lifecycle events are appended after durable state exists, and every normal return writes deterministic JSON and Markdown reports from the 8B3A builder.

Result status is completed, checkpointed, blocked, stalled, or transition_limit. No command-line interface, endpoint composition, Rack AI CLI invocation, or live reasoning is included.
