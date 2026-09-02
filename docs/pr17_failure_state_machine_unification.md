# PR17 Failure State-Machine Unification

Date: 2026-08-31
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`

## Final model

PR17 now uses one authoritative runtime dispatcher and two supporting durable state layers.

- `current_pool` is the authoritative executable progression state.
- `contract.status` is the durable contract lifecycle summary.
- `failure_progress.state` is durable sideband failure metadata, not a second dispatcher.

ATHBA does not resume by switching on `FailureRouteState` values. It resumes by loading the persisted run state and advancing from `current_pool`.

## Authoritative dispatcher

`BehaviorContractCoordinator` advances only from executable pools:

- `tdd_ready`
- `cycle_active`
- `review_ready`
- `repair_ready`
- `approved`

Terminal or externally blocked pools are persisted directly and returned without a second failure-state dispatcher:

- `completed`
- `replan_ready`
- `blocked_executor`
- `blocked_environment`
- `blocked_architecture`
- `blocked_ambiguity`
- `blocked_unclassified`
- `split_required`

## Mechanical failure progression

Mechanical failure progression is the bounded route from execution evidence to a deterministic control-flow outcome.

1. Mechanical execution returns rejected candidate evidence.
2. `FailureObservationBuilder` produces typed observations.
3. `FailureProgressionPolicy` selects a dominant active classification and progression intent.
4. `FailedCandidateRouter` resolves that intent into one executable route.
5. The route updates `current_pool`, trusted revision, retry counts, and durable sideband failure evidence.

Active mechanical classifications are limited to the real producer-backed set exported as `ACTIVE_FAILURE_CLASSIFICATIONS`.

## Dependency and resource replanning

PR17 keeps dependency and resource handling as executable routes, not a separate shadow state machine.

- Resource exhaustion uses bounded packet splitting or fail-closed replanning.
- Syntax/build/bootstrap failures share dependency assessment.
- Dependency decisions persist in `failure_progress`, but execution always resumes from `current_pool`.

## Semantic review boundary

Semantic review verdicts are not mechanical failure classifications.

- `approved` continues normal progression.
- `repair_required` enters bounded semantic repair through `repair_ready`.
- `replan_required` fails closed to `replan_ready`.

These review results persist in cycle review state and semantic repair counters. They do not depend on `FailureProgressionPolicy`, and they do not write synthetic mechanical-failure history entries.

## Persistence and resume

Persistence remains truthful to runtime authority.

- `current_pool` determines the next executable step after reload.
- `failure_progress` preserves audit evidence, retry lineage, dependency decisions, split lineage, repair packets, and blockers.
- Legacy failure classifications still decode for old payloads, but only the active taxonomy is claimed as live PR17 control flow.
- Resume tests prove blocked executor, blocked environment, repair retries, dependency deferrals, and split routes all honor the persisted authoritative pool.

## Outcome

The failure-state contract is now aligned with the actual executable model.

- One authoritative dispatcher: `current_pool`
- One lifecycle summary: `contract.status`
- One durable sideband failure record: `failure_progress.state`
- Separate semantic review state rather than duplicated mechanical-failure vocabulary
