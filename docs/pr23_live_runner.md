# PR23 live runner

The runner accepts `start` and `resume` with a run/project id, exactly one
requirement source, Python/pytest paths, state/evidence roots, and an optional
typed checkpoint. It delegates all lifecycle rules to `StrictTddRunController`.

`StrictTddLiveRunCompositionFactory` wires the existing feature composition,
repositories, lifecycle evidence, report writer, real-compatible local-primary
reasoning adapter, and Rack AI CLI gateway. Its injected gateway seams make
deterministic tests possible without live calls.

Exit codes: 0 success/checkpoint, 2 blocked, 3 stalled, 4 limit, 5 recovery, 6 input/configuration. Stdout is one JSON summary; credentials never enter state, events, reports, or stdout.
