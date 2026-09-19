# PR23 Development Process and Preferred Routing Catalogue

## Status

Documentation-only catalogue for ATHBA's strict-TDD path.

This document describes ATHBA software-development stages and their preferred generic execution route. Internal stage names never cross into Rack AI.

The connector contract is `docs/pr23_generic_rack_ai_connector_contract.md`.

## Three execution surfaces

ATHBA distinguishes three surfaces:

```text
1. ATHBA ReasoningGateway
   Stateless structured reasoning; no trusted worktree mutation.

2. AiWorkspaceExecutionPort
   Bounded model-driven repository/workspace change through Rack AI or another backend.

3. Deterministic ATHBA service
   Parser, adapter, command, regression, Git/CAS, and evidence operations with no model.
```

PR23 does not add a universal Rack AI `execution_form` field. The connector method or endpoint identifies the workspace operation.

## Generic capabilities

Only broad model classes cross the workspace connector:

```text
reasoning
coding
visual
audio
```

A workspace job may require more than one, for example `[reasoning, coding]`.

## Priority policy

Rack AI's global vocabulary is:

```text
low
medium
high
paramount
```

ATHBA's outbound vocabulary is deliberately narrower:

```text
low
medium
```

ATHBA may never submit `high` or `paramount`.

- `low`: background ATHBA work that may wait behind normal rack demand.
- `medium`: ordinary ready ATHBA work, including a task that blocks progress inside an ATHBA project.

High and paramount are reserved for other authorized rack workloads or operator/system policy. This allows interactive or urgent work to reclaim capacity from slow-burn ATHBA development.

ATHBA may maintain richer internal critical-path ordering, but the connector maps it only to low or medium.

## Routing catalogue

| ATHBA stage | Surface | Generic capability | Complexity | Large context | ATHBA outbound priority | Current preferred result | Mutation rights |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Behavior planning | ATHBA ReasoningGateway | reasoning | medium/large | derived | medium | current primary reasoning route | no repository mutation |
| Independent Gatekeeper atomization | ATHBA ReasoningGateway | reasoning | medium/large | derived | medium | current primary reasoning route | no repository mutation |
| Complete scenario authoring | Workspace connector | reasoning + coding | medium | normally false | medium | reasoning-plus-coding worker | declared test path only; scenario remains planning material |
| Scenario structural validation | deterministic adapter | none | n/a | n/a | n/a | no model | no production mutation |
| Scenario intent review | ATHBA ReasoningGateway | reasoning | medium | derived | medium | current primary reasoning route | no repository mutation |
| Scenario repair | Workspace connector | reasoning + coding | medium | inherited | medium | reasoning-plus-coding worker | exact prior test candidate only |
| Frontier decomposition/materialisation | deterministic adapter | none | n/a | n/a | n/a | no model | canonical test frontier only |
| RED boundary validation | deterministic execution | none | n/a | n/a | n/a | no model | no production mutation |
| Frontier implementation, normal tier | Workspace connector | coding | small | false | low/medium | least-scarce coding worker | allowed production paths; test immutable |
| Mechanical frontier repair, normal tier | Workspace connector | coding | small | false | medium | least-scarce coding worker | current production candidate only |
| Frontier implementation, stronger tier | Workspace connector | reasoning + coding | medium | evidence-based | medium | reasoning-plus-coding worker | same frontier/base/paths |
| Focused GREEN | deterministic command | none | n/a | n/a | n/a | no model | no model mutation |
| Accumulated regression | deterministic command | none | n/a | n/a | n/a | no model | no model mutation |
| Regression repair, normal tier | Workspace connector | coding | medium | evidence-based | medium | qualified coding worker | bounded production conflict set |
| Regression repair, stronger tier | Workspace connector | reasoning + coding | medium | evidence-based | medium | reasoning-plus-coding worker | same bounded conflict set |
| Canonical promotion | deterministic Git/CAS | none | n/a | n/a | n/a | no model | exact accepted revision only |
| Senior behavior review | ATHBA ReasoningGateway | reasoning | medium | derived | medium | current primary reasoning route | no direct repository mutation |
| Semantic behavior repair | Workspace connector | reasoning + coding | medium/large | derived | medium | reasoning-plus-coding worker | production paths; accepted tests immutable |
| Final Gatekeeper reconciliation | ATHBA ReasoningGateway plus deterministic evidence | reasoning | large | normally true | medium | large-context reasoning route | no repository mutation |
| Engineering refactoring | future PR21 | not approved here | not approved | not approved | low/medium only when designed | deferred | behavior frozen |

## Current deployment mapping

The catalogue names current expected results only for qualification. ATHBA runtime code does not request these IDs.

```text
Qwen/local-coder
  capabilities: coding
  qualified envelope: small bounded coding work

Gemma/local-primary
  capabilities: reasoning, coding
  qualified envelope: medium/large reasoning and coding work
```

A future backend can map the same generic request differently.

## Stage details

### Complete scenario authoring

ATHBA owns the meaning. It submits a workspace job equivalent to:

```text
capabilities: [reasoning, coding]
complexity: medium
requires_large_context: derived from actual context
priority: medium
```

The candidate remains subject to:

- strict structural validation;
- independent intent review;
- four actual submissions maximum;
- previous-candidate repair when lineage exists;
- no-candidate fresh retry when no source exists;
- no fifth attempt.

### Scenario repair

The same generic profile is used:

```text
[reasoning, coding], medium complexity, medium priority
```

ATHBA supplies exact prior source/ref/SHA and feedback. Rack AI sees a generic workspace change, not a scenario repair.

### Frontier implementation

Normal tier:

```text
capabilities: [coding]
complexity: small
requires_large_context: false
priority: low or medium
```

The worker sees only the active frontier, cannot modify tests, and may change only allowed production paths.

Stronger tier after ATHBA proves normal-tier exhaustion:

```text
capabilities: [reasoning, coding]
complexity: medium
priority: medium
```

The `work_id`, frontier, base SHA, allowed paths, accepted tests, and acceptance contract remain unchanged.

### Deterministic stages

These never become model jobs:

- structural test validation;
- scenario fragmentation;
- frontier materialisation;
- RED evidence analysis;
- focused GREEN;
- accumulated regression;
- revision comparison/promotion;
- evidence catalogue construction.

## Queue interaction

ATHBA owns one semantic ledger and submits only work that is ready and dispatchable.

Rack AI owns a generic queue of those already-ready jobs.

```text
ATHBA semantic state
  -> ready and undispatched
  -> map to generic profile
  -> submit once
  -> Rack AI queues/selects/executes
  -> generic terminal result
  -> ATHBA interprets result
  -> next ATHBA work may become ready
```

Rack AI never receives ATHBA dependency edges and never decides that one behavior precedes another.

## Routing correctness gates

Concurrency is not part of the first acceptance test.

Sequential proof order:

1. reasoning-plus-coding scenario job selects a suitable stronger worker;
2. coding-only small job selects the least-scarce sufficient coding worker;
3. stronger generic fallback selects a reasoning-plus-coding worker;
4. selection evidence matches execution provenance;
5. one tiny ATHBA feature completes sequentially;
6. ReservationBook completes sequentially;
7. only then test multi-GPU concurrency, high/paramount preemption, ComfyUI drain, or idle capacity.

## Failure ownership

| Event | Owner |
| --- | --- |
| Candidate structural/semantic result | ATHBA |
| Model no-candidate result after verified invocation | ATHBA attempt accounting using backend evidence |
| Worker/model/resource selection | Rack AI |
| Executor/transport/worktree failure | Rack AI |
| Focused GREEN/regression result | ATHBA deterministic services |
| Normal-tier exhaustion and stronger-route authorization | ATHBA |
| Source priority rejection | connector/Rack AI admission boundary |
| Selection/provenance mismatch | cross-boundary fail closed |

## Invariants

- ATHBA never sends software-engineering stage names to Rack AI.
- ATHBA never emits priority above medium.
- Priority never changes capability.
- Capability never changes semantic readiness.
- Rack AI never sequences ATHBA dependencies.
- The connector method selects the workspace operation; no PR23 `execution_form` field is required.
- Model identity never bypasses deterministic acceptance.
- The strict test grammar and frontier engine remain frozen.