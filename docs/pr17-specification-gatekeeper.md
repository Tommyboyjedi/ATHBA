# PR17 — Specification Gatekeeper and Test-Evidence Reconciliation

This document is the source-controlled implementation contract for PR17. It matches the current PR17 description as of 2026-08-30.

## Goal

Prove one complete ATHBA development path from a component-level architectural requirement through implementation and back to an independent specification checklist, including durable and bounded recovery or replanning when autonomous Tester or Developer work fails.

## Independent inputs

The same original component requirement is sent independently to two paths:

1. Behavior Planner path: produces the bounded Behavior Contract and drives the Tester -> Developer -> Senior Reviewer loop.
2. Specification Gatekeeper path: atomizes the original source requirement into an independent checklist of atomic factual obligations.

The Behavior Planner must not receive the Gatekeeper checklist up front. The two interpretations remain independent so final reconciliation can expose omissions.

## Gatekeeper responsibility

The Gatekeeper atomizer has one job: convert the original requirement into a meticulous checklist of atomic obligations or facts. It must not prescribe implementation, tests, or repair strategy during atomization.

## Final reconciliation rule

After development, the final reconciler asks only:

> Is there an accepted unit test at the final trusted revision that proves this checklist item?

The answer is `YES` or `NO`. `NO` is valid and remains visible. A `YES` must be backed by concrete accepted unit-test evidence at the final trusted revision. There is no fallback to code inspection, reviewer opinion, or implied coverage.

## Normal progression

```text
component requirement
 -> Behavior Contract
 -> dynamic next-behavior selection
 -> Tester RED candidate
 -> mechanical RED validation
 -> accepted RED revision
 -> Developer GREEN candidate
 -> mechanical acceptance
 -> Senior Reviewer
 -> accepted semantic revision
 -> mark requirement complete
 -> select next ready requirement
 -> repeat
 -> final checklist reconciliation
```

## Invariants

- Only an accepted revision may become the base of the next phase.
- ATHBA persists the trusted revision it advances.
- A failed candidate never silently becomes the semantic base.
- Senior Review remains distinct from Rack AI mechanical acceptance.
- Persisted `BehaviorContractRunState.contract` is authoritative after replanning or prerequisite synthesis.
- Gatekeeper independence must be preserved through persistence and resume.

## Ownership boundary

ATHBA owns development semantics: Behavior Contracts, TDD planning, failure interpretation, dependency replanning, Gatekeeper state, and final reconciliation. Rack AI owns worker selection, worktrees, bounded execution, generic path policy, and accepted candidate materialization.

## Failure progression contract

Every unaccepted RED or GREEN candidate becomes durable `FailureObservation` evidence. ATHBA may identify several plausible classifications, then applies the deterministic priority policy to choose one dominant classification. The chosen decision and progression state must be persisted before resume.

The current exhaustive policy classifications are:
- `executor_infrastructure_failure`
- `environment_failure`
- `resource_limit_failure`
- `syntax_or_parse_failure`
- `build_or_link_failure`
- `test_collection_or_bootstrap_failure`
- `security_or_execution_policy_violation`
- `change_scope_violation`
- `dependency_or_prerequisite_failure`
- `tester_candidate_defect`
- `developer_candidate_defect`

## Definition of done

PR17 is complete when:
- a component requirement produces an independent validated checklist;
- that checklist remains independent from the initial Behavior Planner path;
- accepted TDD evidence can be mapped to checklist obligations;
- missing proof remains visible;
- targeted gaps can re-enter the TDD lane without changing Rack AI;
- final reconciliation uses strict accepted-test `YES` or `NO` semantics at the final trusted revision;
- persistence and resume preserve authoritative state;
- Rack AI boundaries remain unchanged.
