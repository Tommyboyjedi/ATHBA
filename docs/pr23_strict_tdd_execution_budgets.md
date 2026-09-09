# PR23 strict-TDD execution budgets

`DevelopmentWorkUnit` retains its 900-second default for generic and legacy
callers. The active strict-TDD path uses one injected typed policy instead of
scattered factory literals:

| Work kind | Ceiling |
| --- | --- |
| Scenario initial draft | 300 seconds |
| Scenario repair | 300 seconds |
| Active-frontier Developer | 300 seconds |
| Regression repair | 450 seconds |
| Behavior-review repair | 600 seconds |
| Generic fallback | 900 seconds |

These are external wall-clock ceilings for one Rack AI work-unit invocation.
They are independent of scenario/Developer retry caps, Rack AI internal retries,
deterministic regression timeouts, reasoning timeouts, and whole-proof lifetime.

`StrictTddExecutionBudgets` validates positive integer seconds and prevents a
strict-TDD small-work budget exceeding the generic fallback.
`StrictTddExecutionBudgetPolicy` maps only `StrictTddWorkKind`; no project,
feature, domain, model output, or failure message participates in selection.
The feature composition root injects the production policy into every active
Tester/Developer/repair factory.

The selected kind and effective timeout are held by the work unit, carried to the
Rack AI request limits, and persisted with scenario attempts when applicable.
Older attempt records without this optional metadata remain readable.

Rack AI remains responsible for terminal worker packets. ATHBA's transport allows
bounded cleanup beyond the configured budget. A 300-second unit without a terminal
packet or returned transition by about 360 seconds is an
