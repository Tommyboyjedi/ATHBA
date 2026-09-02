# PR23 ATHBA Routing and Generic Rack AI Connector Implementation Plan

## Status

Documentation-only implementation plan. Runtime implementation begins only after the revised boundary is approved.

The plan intentionally separates:

- ATHBA internal software-development routing;
- the backend-neutral AI execution port;
- the generic Rack AI connector;
- Rack AI's model/resource selection;
- later multi-GPU and competing-workload optimization.

## Corrections from the first plan

The earlier plan proposed sending ATHBA work kinds and semantic capability labels to Rack AI.

The revised plan prohibits that.

Rack AI receives only:

```text
capabilities: reasoning | coding | visual | audio
complexity: small | medium | large
requires_large_context: true | false
priority: low | medium | high | paramount
execution form and generic safety constraints
opaque work/submission identity
```

All scenario, frontier, Tester, Developer, repair, review, dependency, and escalation meaning remains inside ATHBA.

## Current versus target

| Concern | Current state at PR23 head | Revised target | Owner | Phase |
| --- | --- | --- | --- | --- |
| Strict scenario grammar | implemented and frozen | unchanged | ATHBA | — |
| Deterministic frontier decomposition | implemented and frozen | unchanged | ATHBA | — |
| Internal development-stage model | dispersed through PR23 state/services | small explicit internal routing catalogue | ATHBA | 1 |
| Backend abstraction | Rack AI gateway types are visible near application orchestration | polymorphic `AiExecutionPort` with backend-neutral request/result types | ATHBA | 1 |
| ATHBA-to-Rack AI mapping | current gateway builds Rack AI-specific work requests | dedicated connector maps generic jobs and results | ATHBA connector | 2 |
| Rack AI capability | singular `implementation` | generic set: reasoning, coding, visual, audio | Rack AI | 2 |
| Complexity | small/medium/large exists | retained | Rack AI | 2 |
| Large-context flag | exists | retained | Rack AI | 2 |
| Priority | no agreed four-value boundary | low/medium/high/paramount | cross-repository generic contract | 2 |
| Work kind at Rack AI boundary | first draft proposed software work kinds | prohibited | both | 2 |
| Dependency graph at Rack AI boundary | readiness/dependency fields exist in current work-unit shape | ATHBA remains authoritative; target connector submits only ready jobs | ATHBA | 1/2 |
| Complete scenario authoring | currently reaches generic implementer path | ATHBA maps stage to reasoning+coding medium | ATHBA resolver; Rack AI generic selector | 3 |
| Scenario repair | candidate repair exists | same repair lineage; generic reasoning+coding profile | ATHBA | 3 |
| Scenario intent review | direct reasoning boundary exists | ATHBA internal stage maps to reasoning structured-response job through port | ATHBA | 3, migration may be staged |
| Narrow frontier implementation | strict contract exists | maps to coding small; least-scarce sufficient generic selection | both | 4 |
| Narrow-tier attempt accounting | scenario accounting exists; Developer attempts exist | reusable internal tier state, four actual submissions | ATHBA | 4 |
| Stronger fallback | not implemented | same work, new submission, reasoning+coding medium profile | ATHBA authorizes; Rack AI selects generically | 4 |
| Selection evidence | execution provenance exists in Rack AI PR30 | generic selection decision linked to provenance | Rack AI | 2 |
| ATHBA ready collection | transitions create work directly | one authoritative internal ledger/ready view | ATHBA | 1/4 |
| Rack AI queue | current work-unit execution path | generic queue of already-ready jobs | Rack AI | separate Rack AI scheduling track |
| Shared pool | none | explicitly prohibited | both | — |
| Sequential routing proof | not complete | hard gate before concurrency | both | 5 |
| Concurrency/idle overflow | not implemented | deferred | Rack AI scheduling specification | 8 |
| Three-GPU/ComfyUI arbitration | separate roadmap work | separate Rack AI specification using same generic boundary | Rack AI | 8 |
| Tiny end-to-end proof | incomplete | sequential route completes first | both | 6 |
| ReservationBook proof | incomplete | follows tiny proof only | both | 7 |

## Phase 0 — Review and freeze the revised design

### Repository

ATHBA PR27 documentation branch.

### Goal

Approve:

- software-development semantics remain entirely in ATHBA;
- generic four-capability Rack AI interface;
- priority enum;
- no shared semantic queue;
- polymorphic connector;
- sequential proof before concurrency.

### Completion markers

```text
REVISED_BOUNDARY_APPROVED = YES
RACK_AI_SOFTWARE_ENGINEERING_TERMS = NONE
```

## Phase 1 — ATHBA internal execution profiles and port

### Repository

ATHBA, on a new implementation branch stacked on PR23.

### Goal

Introduce a small internal routing layer without changing live worker selection.

Add concepts equivalent to:

```text
AthbaModelWorkKind
AthbaExecutionProfile
AthbaExecutionProfileResolver
AiExecutionPort
GenericAiJobRequest
GenericAiJobResult
```

`AthbaModelWorkKind` remains internal and may represent:

- behavior planning;
- Gatekeeper atomization;
- scenario authoring/repair;
- scenario intent review;
- frontier implementation/repair;
- regression repair;
- senior review;
- semantic behavior repair;
- final reconciliation.

`AthbaExecutionProfile` contains only generic boundary values:

- capabilities;
- complexity;
- large-context flag;
- priority;
- execution form;
- timeout.

### Non-goals

- no Rack AI request change;
- no live routing change;
- no fallback implementation;
- no concurrency;
- no model or GPU IDs in ATHBA domain code.

### Tests

- every model-executed ATHBA stage has one explicit profile;
- deterministic stages produce no model request;
- scenario authoring maps to reasoning+coding medium;
- frontier tier 1 maps to coding small;
- stronger frontier tier maps to reasoning+coding medium;
- priority mapping uses only low/medium/high/paramount;
- paramount is never a routine default;
- no worker/model/GPU identifiers appear in profile resolver;
- fake connector can drive existing deterministic PR23 composition;
- old Rack AI gateway remains usable behind a compatibility adapter.

### Rollback boundary

Pure ATHBA abstraction. Revert without changing PR23 scenario/frontier state.

## Phase 2 — Generic cross-repository contract and Rack AI connector

### Repositories

- ATHBA connector package;
- Rack AI generic request/parser package.

Use separate PRs with an explicitly versioned wire contract.

### Goal

Introduce the generic request fields:

```text
capabilities[]: reasoning | coding | visual | audio
complexity: small | medium | large
requires_large_context: bool
priority: low | medium | high | paramount
execution_form
work_id
submission_id
idempotency_key
timeout and generic constraints
```

Rack AI must not receive ATHBA work kinds.

The ATHBA `RackAiConnector` implements `AiExecutionPort` and is responsible for transport mapping only.

### Compatibility

- old `capability=implementation` requests remain readable during migration;
- new connector request version is additive;
- old packets remain readable;
- no selection behavior changes until phase 3;
- existing dependency fields may remain readable but are not semantic authority for new connector jobs.

### Non-goals

- no capability-based worker selection yet;
- no scenario route change;
- no escalation;
- no software terminology in Rack AI;
- no live feature proof.

### Tests

- generic request serialization round-trip;
- exact capability enum;
- exact priority enum;
- multi-capability request support;
- unknown capability fails closed;
- unknown priority fails closed;
- complexity and large-context compatibility;
- opaque work/submission identities round-trip;
- duplicate submission is idempotent;
- no ATHBA stage field appears on the wire;
- fake alternative connector proves ATHBA portability;
- old request/packet compatibility.

### Rollback boundary

Both sides retain old request compatibility. New fields can be removed without touching PR23 domain state.

## Phase 3 — Rack AI generic model capability selection

### Repository

Rack AI, on a focused branch stacked after trusted execution/provenance foundations.

### Goal

Replace the current singular implementation-only selection input with generic capability-set selection.

Add generic model/profile metadata equivalent to:

```text
capabilities
max complexity by capability
large-context eligibility
qualification status and evidence
profile version
```

Keep worker runtime/resource/lease state separate from model capability.

Selection algorithm:

1. require all requested capabilities;
2. enforce complexity qualification;
3. enforce large-context requirement;
4. enforce execution form and resource constraints;
5. rank eligible workers by generic least-scarce-sufficient policy and resource state;
6. return durable generic selection evidence;
7. verify selected worker matches execution provenance.

### Current generic registry expectation

```text
local-coder model profile
  capabilities: coding
  qualified envelope: small bounded coding, selected medium bounded repair

local-primary model profile
  capabilities: reasoning, coding
  qualified envelope: medium/large reasoning and coding
```

These names stay in Rack AI configuration only.

### Non-goals

- no scenario or frontier terms;
- no ATHBA dependency logic;
- no idle overflow;
- no preemption;
- no ComfyUI arbitration;
- no adaptive learning;
- no JCode tool-profile change.

### Tests

- `[reasoning, coding]` excludes coding-only workers;
- `[coding]` small includes both current profiles when both qualify;
- least-scarce-sufficient ranking selects coding-only worker;
- reasoning-plus-coding worker remains eligible for stronger profile;
- medium/large complexity constraints are honored;
- large-context filter works;
- low/medium/high/paramount queue order works without changing capabilities;
- no eligible worker returns generic capability-unavailable;
- busy eligible worker yields queued status rather than permanent capability failure;
- same model profile on two runtime workers retains same capabilities;
- resource removal makes only that worker unavailable;
- selection decision and execution provenance must agree;
- old worker config remains readable.

### Sequential Rack AI qualification

Run three one-at-a-time disposable jobs:

1. reasoning+coding medium -> current primary-capable worker;
2. coding small -> current coding worker;
3. reasoning+coding medium using the same opaque work lineage -> current primary-capable worker.

No ATHBA feature proof and no concurrency.

### Rollback boundary

Generic selector is isolated in Rack AI. Old compatibility route remains until ATHBA switches.

## Phase 4 — Route complete scenario authoring through the generic connector

### Repository

ATHBA.

### Goal

Map internal complete scenario authoring and scenario repair to:

```text
capabilities: [reasoning, coding]
complexity: medium
requires_large_context: derived, normally false
priority: high while blocking active behavior
execution_form: workspace_change
```

The current Rack AI registry should select a primary-capable worker without ATHBA naming it.

Retain:

- four actual scenario submissions;
- fresh/repair/no-candidate modes;
- exact candidate lineage;
- strict structural adapter;
- independent intent review;
- frozen test grammar;
- no candidate promotion before normal gates.

### Non-goals

- no local-coder scenario route;
- no new decomposition logic;
- no fallback from scenario authoring to coding-only worker;
- no concurrency;
- no ReservationBook proof.

### Tests

- internal stage maps to exact generic profile;
- connector request contains no stage name;
- current selection evidence proves a reasoning+coding worker;
- ATHBA accepts any worker satisfying the generic contract, not one hard-coded ID;
- four-attempt and repair semantics persist across restart;
- infrastructure failure consumes no model attempt;
- approved scenario remains planning material;
- deterministic fragments are unchanged.

### Live qualification

Fresh neutral scenario-authoring-only proof ending after:

- approved complete scenario;
- structural and intent acceptance;
- deterministic decomposition.

## Phase 5 — Coding-only frontier route and stronger generic fallback

### Repository

ATHBA; Rack AI selection behavior already exists from phase 3.

### Goal

Tier 1 mapping:

```text
capabilities: [coding]
complexity: small
priority: high or medium from critical path
```

After four genuine Tier-1 model failures, ATHBA retains the same internal work and maps Tier 2 to:

```text
capabilities: [reasoning, coding]
complexity: medium
priority: high
```

Rack AI sees generic requests only.

### Persisted ATHBA state

- stable work ID;
- current tier;
- submissions consumed per tier;
- unique submission IDs;
- active frontier/test identity;
- base ref/SHA and allowed paths;
- candidate/no-candidate history;
- repair and escalation parent;
- connector acknowledgement;
- selection decision reference;
- execution result/provenance reference.

### Non-goals

- no coder-primary-coder bounce;
- no fifth attempt in either tier;
- no idle-primary overflow;
- no shared queue;
- no same-project parallel mutation;
- no fixture-specific routing.

### Tests

- Tier 1 produces coding small generic request;
- current Rack AI selector chooses coding worker;
- four actual model failures trigger one internal tier transition;
- infrastructure failures do not consume attempts;
- Tier 2 produces reasoning+coding medium generic request;
- objective, base, active test, paths, and accepted evidence remain immutable;
- latest candidate is supplied when available;
- no-candidate history is supplied without fabricated source;
- restart preserves tier and attempts;
- stronger-tier success still passes focused GREEN and deterministic regression;
- both tiers exhausted produces ATHBA capability block;
- no software escalation field appears on Rack AI wire.

## Phase 6 — Sequential tiny-feature proof

### Goal

Prove routing correctness before concurrency.

Required one-at-a-time route:

1. Behavior Planner and Gatekeeper reasoning requests;
2. complete scenario authoring through reasoning+coding generic request;
3. deterministic decomposition;
4. coding small active-frontier request;
5. focused GREEN and deterministic regression;
6. further sequential frontiers;
7. deterministic forced-selection test for stronger generic profile, or a naturally exhausted narrow tier without fixture-specific prompt changes;
8. checkpoint and new-process resume;
9. senior behavior review;
10. final reconciliation;
11. final target tests pass.

### Hard evidence

- each generic request profile;
- each Rack AI selection decision;
- execution provenance equality;
- no concrete worker IDs in ATHBA request construction;
- no concurrent external jobs;
- no repeated completed work;
- no change to test grammar or JCode tools.

### Stop condition

If reasoning-plus-coding scenario work and both narrow implementation tiers cannot complete the same tiny feature under the frozen contract, stop for architecture simplification review.

## Phase 7 — Fresh ReservationBook proof

Run only after Phase 6 passes.

Required:

- fresh repository and state;
- independent Behavior Planner/Gatekeeper inputs;
- primary-capable complete scenario authoring;
- deterministic strict frontiers;
- coding-only preferred narrow implementation;
- stronger generic fallback when required;
- persistence/restart;
- full accepted regression;
- behavior review;
- final Gatekeeper YES/NO test reconciliation;
- no ReservationBook-specific routing or harness accommodation.

PR23 remains open until this proof passes or terminates at a legitimate capability/human blocker under the approved contract.

## Phase 8 — Separate Rack AI scheduling specification

This is deliberately outside the initial PR23 merge gate.

A separate Rack AI design must cover:

- three-GPU placement;
- same model profile on 4060 Ti and 4080 Super;
- throughput-aware selection;
- model residency and reload cost;
- ComfyUI/image/video/audio resource leases;
- development slowdown without semantic failure when a GPU is removed;
- queue fairness and ageing;
- idle stronger-worker use;
- multi-project concurrency;
- preemption policy, if any.

It must consume the same generic job contract and must not learn ATHBA software-engineering terms.

## ATHBA dispatch model

ATHBA retains one authoritative semantic work ledger.

A dispatcher:

1. finds semantically ready, undispatched work;
2. enforces ATHBA project mutation and idempotency rules;
3. resolves a generic execution profile;
4. submits every dispatchable item through `AiExecutionPort`;
5. persists acknowledgement;
6. correlates terminal results by `submission_id`;
7. interprets results and unlocks further work.

Rack AI does not receive dependency edges or decide the next behavior.

Version 1 may remain one mutating item per project while still allowing several independent projects to submit ready work.

## Test matrix across phases

### Boundary tests

- no ATHBA stage crosses connector;
- no concrete model/GPU ID in ATHBA domain;
- generic capability set only;
- exact priority enum;
- deterministic stages never call connector;
- fake connector substitution.

### Selector tests

- capability subset filtering;
- complexity envelope;
- large-context filter;
- priority ordering;
- least-scarce-sufficient ranking;
- busy versus unavailable distinction;
- selection/provenance equality.

### State tests

- stable work ID and unique submissions;
- per-tier attempt persistence;
- candidate/no-candidate lineage;
- no fifth attempt;
- no tier bounce;
- stale-base rejection;
- connector receipt replay;
- no shared queue authority.

### Live proof tests

- sequential selection before concurrency;
- primary-capable scenario route;
- coding-only frontier route;
- stronger generic fallback;
- deterministic regression;
- restart;
- final reconciliation.

## Pull-request sequence

Recommended bounded PRs:

1. **ATHBA PR-A — internal profiles and AI execution port**
2. **Cross-repository contract review — generic job v2**
3. **Rack AI PR-B — generic capabilities, priority, selector, selection evidence**
4. **ATHBA PR-C — RackAiConnector and scenario route**
5. **ATHBA PR-D — coding tier and stronger fallback**
6. **Proof PR-E — tiny sequential proof evidence**
7. **Proof PR-F — ReservationBook evidence and PR23 closeout**
8. **Rack AI design PR — three-GPU and competing-workload scheduler**

Do not combine runtime routing, concurrency, and ReservationBook proof into one unreviewable change.

## Explicit non-goals before PR23 proof

- no shared ATHBA/Rack AI queue;
- no Rack AI software stages;
- no Rack AI dependency graph;
- no idle-primary optimization;
- no three-GPU scheduler;
- no ComfyUI preemption design inside ATHBA;
- no dynamic model bake-off;
- no cloud fallback;
- no test-grammar or JCode-tool changes;
- no concurrent routing acceptance test.

## Definition of implementation readiness

Implementation begins only after review confirms:

- internal ATHBA stages are separated from the generic boundary;
- capability vocabulary is reasoning/coding/visual/audio;
- complexity and large-context fields retain their generic meaning;
- priority is low/medium/high/paramount;
- the connector is polymorphic;
- dependencies remain ATHBA-owned;
- Rack AI queues only already-ready generic jobs;
- sequential routing is the first live gate;
- wider GPU scheduling is a separate Rack AI specification.
