# PR23 Worker-Capability Routing Implementation Plan

## Status

Documentation-only implementation plan. Runtime implementation begins only after the routing architecture is reviewed.

## Current versus target

| Capability | Current state at PR23 head | Target state | Owner | Required change | Phase |
| --- | --- | --- | --- | --- | --- |
| Strict scenario grammar | Implemented and frozen | Unchanged | ATHBA | None | — |
| Deterministic frontier decomposition | Implemented and frozen | Unchanged | ATHBA adapters | None | — |
| Complete scenario authoring | Generic Tester work currently reaches the configured implementer route | Requires high-reasoning + behavioral-test-design capability; current mapping selects local-primary | ATHBA descriptor + Rack AI selection | New capability-based request/selection contract | 1–3 |
| Scenario repair | Previous-candidate repair implemented | Same repair protocol on high-reasoning scenario tier | ATHBA + Rack AI | Route by capabilities; preserve candidate lineage | 3 |
| Scenario intent review | Separate reasoning boundary implemented | Unchanged, with selection/protocol evidence | ATHBA | Integrate with new work records only | 3 |
| Frontier implementation | Strict narrow contract implemented | local-coder preferred by capability | ATHBA descriptor + Rack AI selection | Remove concrete-route assumptions; add selection evidence | 2–4 |
| Four actual submissions | Implemented for scenario work | General per-tier attempt state | ATHBA | Extract reusable tier-attempt model without replacing existing semantics | 4 |
| Primary fallback | Not implemented | Four coder submissions then four primary submissions | ATHBA authorizes; Rack AI selects | Tier escalation and preserved lineage | 4 |
| Worker capability metadata | Worker role/model/resource metadata exists | Versioned qualified capability set and constraints | Rack AI | Extend registry | 2 |
| Worker selection evidence | Execution provenance implemented | Durable eligibility and selection decision | Rack AI | New typed decision linked to provenance | 2 |
| Semantic ready-work pool | Existing state machine selects transitions directly | Explicit ready descriptors without duplicating semantic authority | ATHBA | Small ready-work projection | 1/4 |
| Execution queue | Rack AI queue/lease concepts exist | Accept capability-bearing immutable work | Rack AI | Extend existing request/selector/queue path | 1/2 |
| Idle-primary overflow | Not implemented | Designed, later optimisation | Rack AI | Deferred | 7 |
| Priority and ageing | Partial queue concepts | Small priority classes; sophisticated ageing later | Both boundary / Rack AI execution | Minimum for semantic-vs-overflow protection later | 7 |
| Project mutation concurrency | Revision lifecycle/CAS foundations implemented | One mutating lane per project | ATHBA trust + Rack AI lease | Explicit lease/selection invariant | 2/4 |
| Selection/provenance consistency | Provenance only | Fail closed if selected and executed worker differ | Both | Cross-boundary validation | 1/2 |
| Tiny live proof | Not completed | Full primary-scenario/coder-frontier/fallback route | Both | New proof after phases 1–4 | 5 |
| ReservationBook proof | Not completed | Fresh complete proof and Gatekeeper reconciliation | Both | Run only after tiny proof | 6 |

## Phase 1 — Cross-repository work contract

### Repositories

- ATHBA
- Rack AI

### Goal

Introduce compatible typed fields without changing live routing.

ATHBA descriptor adds concepts equivalent to:

- work kind;
- required capabilities;
- preferred capabilities;
- priority class;
- escalation tier;
- attempt number within tier;
- stable work ID and global submission sequence.

Rack AI request parsing accepts and persists those fields. Existing requests remain readable and retain current behavior.

### Non-goals

- no new worker selection policy;
- no scenario route change;
- no escalation;
- no live proof;
- no tool/profile changes.

### Tests

- serialization and backward compatibility;
- stable work identity across submissions;
- no concrete worker/GPU identifiers in ATHBA semantic descriptors;
- unknown required capability fails closed once capability selection is enabled, but phase-1 compatibility mode preserves existing requests;
- request/packet round-trip.

### Rollback boundary

The contract fields are optional and backward compatible. The phase can be reverted without touching strict-TDD state.

### Completion markers

```text
CROSS_REPO_WORK_DESCRIPTOR = PASS
BACKWARD_COMPATIBILITY = PASS
ROUTING_BEHAVIOR_CHANGED = NO
```

## Phase 2 — Rack AI capability selection

### Repository

Rack AI

### Goal

Extend existing worker/model/resource registration and selector code with:

- versioned capability records;
- qualification status and evidence refs;
- constraints;
- deterministic eligibility;
- durable `WorkerSelectionDecision`;
- consistency check against `WorkerExecutionProvenance`.

Initial deployment mappings:

- local-primary: high reasoning, behavioral test design, semantic review, and coding capabilities;
- local-coder: bounded code edit, repository navigation, compiler/test repair, structured tool use, qualified with constraints.

### Non-goals

- no adaptive learning;
- no idle overflow;
- no preemption;
- no cloud workers;
- no change to JCode minimal profile;
- no ATHBA semantic logic in Rack AI.

### Tests

- eligible and ineligible sets with explicit reasons;
- no eligible worker fails closed;
- preferred capable worker selected when free;
- fallback-capable worker remains eligible but is not chosen in preferred tier;
- qualification constraints honored;
- leases and concurrency capacity honored;
- selection decision persisted for accepted, rejected, timeout, and no-candidate results;
- execution provenance matches selection;
- mismatch fails closed;
- existing worker configuration remains readable.

### Live qualification

A disposable Rack AI-only smoke submits two capability descriptors and proves:

- scenario-authoring capability selects local-primary;
- narrow-code capability prefers local-coder;
- no ATHBA feature proof is run.

### Rollback boundary

Capability metadata and selector changes are isolated to Rack AI. Existing role-based selection remains available until phase 3 switches ATHBA requests.

### Completion markers

```text
RACK_AI_CAPABILITY_REGISTRY = PASS
WORKER_SELECTION_DECISION = PASS
SELECTION_PROVENANCE_MATCH = PASS
```

## Phase 3 — Primary scenario authoring

### Repository

ATHBA, using the phase-1/2 Rack AI contract.

### Goal

Change complete scenario authoring and repair to request:

```text
high_reasoning
behavioral_test_design
code_artifact_authoring
```

The current Rack AI mapping should select local-primary. The existing candidate-source, candidate-lineage, strict structural validation, intent-review boundary, no-candidate accounting, and four-submission limit remain intact.

### Non-goals

- no local-coder scenario fallback;
- no test grammar change;
- no new fragment logic;
- no idle-primary overflow;
- no ReservationBook proof.

### Tests

- scenario work descriptor requires the correct capabilities;
- selected worker evidence is local-primary under current registry;
- ATHBA does not name local-primary in semantic application code;
- attempt 1 fresh / attempts 2–4 repair or fresh-retry semantics retained;
- infrastructure failure does not consume primary scenario submissions;
- structurally invalid and semantic-repair routes remain distinct;
- intent review remains a separate stateless call;
- approved scenario is frozen but not promoted as active test;
- deterministic adapter output is unchanged.

### Live proof

One tiny scenario-authoring-only proof using a fresh neutral domain. It ends after an approved scenario and deterministic decomposition; it does not yet claim the whole feature.

### Rollback boundary

Revert the capability requirement for scenario authoring; the underlying strict-drafting state remains unchanged.

### Completion markers

```text
PRIMARY_SCENARIO_AUTHORING = PASS
SCENARIO_REPAIR_PRIMARY = PASS
DETERMINISTIC_FRONTIERS_UNCHANGED = YES
```

## Phase 4 — Narrow coder route and bounded primary fallback

### Repositories

- ATHBA: tier state, escalation authorization, candidate lineage, acceptance progression.
- Rack AI: capability-based selection already implemented in phase 2; no ATHBA failure semantics added.

### Goal

For `frontier_implementation` and bounded mechanical repair:

1. submit narrow tier requiring bounded code-edit capabilities and preferring the qualified narrow worker;
2. allow at most four actual local-coder submissions;
3. on truthful model-originated exhaustion, preserve immutable work and escalate to primary-eligible tier;
4. allow at most four actual local-primary submissions;
5. after both tiers exhaust, persist `capability_blocked` and stop.

### State to persist

- work ID;
- tier;
- attempts consumed and maximum per tier;
- global submission sequence;
- candidate/no-candidate history;
- last safe candidate branch/ref/SHA;
- repair parent and escalation parent;
- selection decision IDs;
- execution packet IDs;
- base ref/SHA;
- allowed paths;
- active frontier and accepted test identity.

### Non-goals

- no coder-primary-coder bounce;
- no fifth attempt in either tier;
- no idle overflow;
- no adaptive routing;
- no same-project parallel mutations.

### Tests

- local-coder is preferred for narrow work under current registry;
- four coder failures trigger exactly one tier transition;
- model-originated no-candidate failures count;
- external failures do not count;
- latest candidate is supplied to primary repair;
- no-candidate history is supplied without fabricated source;
- objective, frontier, base, accepted tests, and paths are immutable across tier transition;
- process restart preserves tier and counters;
- primary success proceeds through focused GREEN and deterministic regression;
- both tiers exhausted yields capability block;
- stale-base candidate is rejected;
- canonical promotion remains serialized.

### Live qualification

Use deterministic fakes first, then a disposable narrow task that can force the fallback route without changing test grammar or prompts for a named fixture.

### Rollback boundary

Tiered escalation is isolated behind the work descriptor and tier-state domain. The strict microcycle remains valid without fallback.

### Completion markers

```text
LOCAL_CODER_PREFERRED_NARROW = PASS
LOCAL_PRIMARY_BOUNDED_FALLBACK = PASS
PER_TIER_RESUME = PASS
INFINITE_BOUNCE = NO
```

## Phase 5 — Tiny full live proof

### Goal

One fresh feature must complete:

1. independent Behavior Planner and Specification Gatekeeper;
2. local-primary scenario authoring;
3. independent intent approval;
4. deterministic fragment decomposition;
5. multiple valid RED frontiers;
6. local-coder narrow GREEN work where successful;
7. primary fallback either naturally or through a generic controlled qualification path;
8. deterministic regression with zero reasoning calls;
9. canonical promotions;
10. first-regression-clear checkpoint;
11. genuinely new-process resume without repeated work;
12. behavior review;
13. final reconciliation;
14. passing final target tests.

The proof may not justify any new tool, test grammar, retry, or fixture-specific harness change.

### Completion markers

```text
TINY_CAPABILITY_ROUTING_PROOF = PASS
PRIMARY_SCENARIO_ROUTE = PASS
CODER_NARROW_ROUTE = PASS
PRIMARY_FALLBACK_ROUTE = PASS
LIVE_RESUME = PASS
FINAL_RECONCILIATION = PASS
```

## Phase 6 — Fresh ReservationBook proof

### Goal

Run the original larger proof only after phase 5 passes.

Required evidence:

- independent Gatekeeper checklist;
- independent Behavior Contract;
- scenario and frontier histories;
- worker selection decisions and execution provenance;
- coder/primary tier transitions;
- trusted revision progression;
- deterministic accumulated tests;
- behavior review;
- every checklist item reconciled YES/NO against accepted tests at the final trusted revision.

### Stop rule

A model violating an existing contract follows normal repair/escalation. A genuine generic invariant violation may be fixed only under `pr23_live_proof_change_control.md`.

### Completion markers

```text
RESERVATIONBOOK_CAPABILITY_ROUTING_PROOF = PASS
GATEKEEPER_FULL_RECONCILIATION = PASS
PR23_MERGE_GATE = PASS
```

## Phase 7 — Post-proof optimisation

Only after PR23's tiny and ReservationBook proofs pass:

- idle-primary overflow;
- priority/ageing refinement;
- multi-project throughput;
- historical success-rate routing;
- worker bake-offs;
- wider ready-ticket pools;
- future cloud or human escalation interfaces.

### Initial idle-overflow policy

- high-reasoning and review work has priority;
- escalated narrow work precedes optional overflow;
- no new overflow lease while high-reasoning work waits;
- no preemption in version 1;
- a running short overflow task finishes;
- selection evidence records `idle_overflow`.

## Migration and compatibility

- Cross-repository fields are added as optional before they become required.
- Old Rack AI packets remain readable; new capability-routing proofs require selection evidence.
- Existing PR23 scenario and attempt state remains readable.
- Existing concrete worker provenance remains unchanged.
- Capability versions and policy versions are persisted so restart cannot reinterpret historical selections.
- Current worker names remain deployment configuration, not ATHBA domain rules.

## Structural acceptance matrix

| Invariant | Required proof |
| --- | --- |
| ATHBA names capabilities, not hardware | static dependency/AST tests |
| Rack AI selects concrete workers | selector tests and live disposable evidence |
| Scenario uses primary mapping | selection decision + execution provenance |
| Frontiers are deterministic | existing adapter tests unchanged |
| Coder preferred for narrow work | eligibility/selection tests |
| Primary fallback is bounded | per-tier state-machine tests |
| No fifth attempt | deterministic counters and restart tests |
| Infrastructure does not consume model budget | failure-origin tests |
| Selection equals execution | packet consistency tests |
| One mutating lane per project | lease/CAS tests |
| Resume does not repeat work | controller receipt/replay tests |
| No fixture accommodation | change-control audit |

## PR23 closure decision

PR23 must remain an open draft while this work is designed and implemented. It contains the strict-TDD foundation required by the routing proposal, but its declared end-to-end proof gates remain unmet.

PR23 becomes eligible for review/merge only after phases 1–6 complete. Closing it now would incorrectly imply abandonment or completion; merging it now would incorrectly claim a functioning live route.
