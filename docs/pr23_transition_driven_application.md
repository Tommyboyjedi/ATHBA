# PR23 Transition-Driven Application

## Purpose

The former run-to-completion APIs could draft, execute several frontiers, run regression, advance revisions, review a behavior, and reconcile a feature before returning. A controller outside those calls could not truthfully stop at a persisted checkpoint or distinguish a transition from a derived evidence string.

## One-transition APIs

`StrictMicrocycleService.advance`, `StrictFeatureScenarioExecutor.advance`, and `StrictTddFeatureApplicationService.advance` return immutable typed results. The result records its typed kind, prior and resulting status, behavior/scenario/frontier identity, concrete canonical and working ref/SHA values, candidate revision, evidence references, external-reasoning/Rack AI/regression invocation flags, next-transition availability, and blocker or replan reason.

Microcycle kinds include accepted RED, passing frontier observation, Developer acceptance/rejection, deterministic regression outcomes, frontier advancement, scenario completion, review, repair, behavior completion, exhaustion, and blocking. Scenario and feature kinds describe the smaller draft/revision/microcycle and plan/selection/reconciliation transitions.

## Persistence and lifecycle

Each advance performs its effect, persists strict-TDD state, persists lifecycle ref state where applicable, and only then returns the typed result. Accepted RED and Developer work advance only the managed working ref. Regression-clear promotion advances the canonical base only when it equals the persisted working revision. The returned result reads the resulting lifecycle state rather than reconstructing refs.

## Compatibility loops

The legacy `run()` and `execute()` APIs are bounded loops over `advance()`. They stop on completion, a blocker, replan, retry exhaustion, accumulated-regression boundary, or the explicit transition safety guard. They do not retain a second workflow state machine.

## Checkpoints and stalls

Future checkpoint code selects `MicrocycleTransitionKind.FRONTIER_RED_ACCEPTED`, `REGRESSION_CLEAR`, and `SCENARIO_COMPLETED`; it does not parse `evidence_refs` prose. Every result includes a `TransitionFingerprint` made only from persisted status, behavior/scenario/frontier identity, canonical/working SHA, retry counters, and pending action. Equal fingerprints identify an identical persisted state and requested action with no progress, without incidental timestamps or evidence text.

## Boundaries

This session intentionally emits no lifecycle events, starts no controller or CLI, and does not compose or call live dependencies. Rack AI remains a capability boundary; no Rack AI source or configuration is changed.


## Atomic-transition hardening

The transition APIs now persist an explicit pending action in `MicrocycleState`.
A normal frontier progresses through: observe frontier, submit Developer work,
verify the Developer candidate is GREEN, run deterministic regression, promote
the canonical base, then advance the frontier. No one transition combines two
of those effects. Regression and behavior repairs use the same submit,
regress, and promotion boundaries. Scenario drafting persists a Tester
candidate before a later independent intent-review transition. Feature planning
persists project, contract, Gatekeeper checklist, behavior selection, scenario
execution, behavior recording, reconciliation, and completion as separate
feature transitions.

Transition result flags describe only the current action. In particular,
scenario candidate submission sets only `rack_ai_invoked`; intent review sets
only `external_reasoning_invoked`; regression execution sets only
`deterministic_regression_invoked`; canonical promotion sets none of them.
