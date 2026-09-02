# PR23 Generic Workspace Routing Implementation Plan

## Status

Documentation-only implementation plan. Runtime work begins only after the revised boundary is approved.

The plan is intentionally smaller than earlier PR27 drafts.

## Approved boundary to implement

ATHBA owns all software-development meaning and maps ready model work to:

```text
capabilities: reasoning | coding | visual | audio
complexity: small | medium | large
requires_large_context: true | false
priority: low | medium   # ATHBA outbound limit
opaque work/submission identity
bounded workspace objective and constraints
```

Rack AI owns generic model/resource selection and the bounded workspace executor.

PR23 does not require:

- ATHBA work kinds in Rack AI;
- an `execution_form` field;
- structured reasoning through Rack AI;
- visual/audio executors;
- shared semantic queues;
- ComfyUI arbitration;
- concurrency optimization.

## Current versus target

| Concern | Current state | PR23 target | Owner |
| --- | --- | --- | --- |
| Workspace operation | current work-unit maps to bounded change path | preserve | Rack AI |
| Workload label | `application-development` MVP | retain compatibility; new connector treats workspace operation generically | connector/Rack AI |
| Capability | singular `implementation` | non-empty set: reasoning, coding, visual, audio | Rack AI contract |
| Complexity | small/medium/large | preserve | Rack AI |
| Large context | boolean exists | preserve | Rack AI |
| Priority | absent | global enum low/medium/high/paramount; ATHBA capped at medium | both boundary |
| ATHBA internal routing | dispersed stage-specific calls | explicit internal profile resolver | ATHBA |
| Backend abstraction | Rack AI gateway visible near domain | `AiWorkspaceExecutionPort` | ATHBA |
| Worker registry | role/model/resource metadata | generic capability/qualification metadata | Rack AI |
| Selection | minimal vs non-minimal heuristic | generic eligibility and least-scarce-sufficient ranking | Rack AI |
| Selection evidence | execution provenance only | selection decision linked to provenance | Rack AI |
| Scenario authoring | generic implementer route | reasoning+coding, medium, medium priority | ATHBA profile + Rack AI selector |
| Frontier implementation | current narrow contract | coding, small, low/medium priority | ATHBA profile + Rack AI selector |
| Stronger fallback | absent | same work, reasoning+coding, medium, medium priority | ATHBA authorizes |
| Dependencies | current request can carry `depends_on` | ATHBA withholds blocked jobs; no Rack AI sequencing authority | ATHBA |
| Tiny proof | incomplete | sequential proof | both |
| ReservationBook | incomplete | follows tiny proof | both |

## Phase 0 — Approve the documentation

Approve these decisions:

- Rack AI remains ignorant of software engineering;
- PR23 uses one bounded workspace operation;
- model capabilities are reasoning/coding/visual/audio;
- ATHBA can emit only low/medium priority;
- high/paramount remain available for rack-wide external/operator demand;
- no shared semantic pool;
- routing is proven sequentially before concurrency.

Completion:

```text
BOUNDARY_APPROVED = YES
ATHBA_MAX_OUTBOUND_PRIORITY = MEDIUM
PR23_EXECUTION_FORM_FIELD = ABSENT
```

## Phase 1 — ATHBA internal profile resolver and workspace port

### Repository

ATHBA, on a new branch stacked on PR23.

### Goal

Add internal concepts equivalent to:

```text
AthbaModelWorkKind
AthbaWorkspaceExecutionProfile
AthbaWorkspaceExecutionProfileResolver
AiWorkspaceExecutionPort
WorkspaceJobRequest
WorkspaceJobResult
```

`AthbaModelWorkKind` remains internal and may include scenario authoring, frontier implementation, repair, and stronger fallback.

Boundary profile fields:

```text
capabilities
complexity
requires_large_context
priority: low | medium
timeout
```

The port method identifies the operation:

```text
submit_workspace_change(...)
```

No `execution_form` field is introduced.

### Priority invariant

- profile resolver can return only low/medium;
- connector rejects high/paramount even if constructed through an unsafe cast or malformed input;
- ATHBA internal critical-path ordering may be richer but cannot cross the boundary above medium.

### Non-goals

- no Rack AI schema change;
- no live route change;
- no fallback;
- no worker/GPU names;
- no reasoning-gateway migration.

### Tests

- every model-driven workspace stage has one profile;
- deterministic stages produce no workspace request;
- scenario authoring maps to reasoning+coding/medium/medium;
- frontier tier 1 maps to coding/small/low-or-medium;
- stronger tier maps to reasoning+coding/medium/medium;
- high/paramount cannot be constructed for ATHBA outbound jobs;
- no concrete model/worker/GPU identifiers in resolver;
- fake workspace connector drives existing PR23 transitions;
- current Rack AI gateway remains usable behind an adapter.

## Phase 2 — Versioned generic workspace request

### Repositories

- ATHBA connector package;
- Rack AI request/parser package.

### Goal

Add a backward-compatible workspace request carrying:

```text
source_system
work_id
submission_id
idempotency_key
capabilities[]
complexity
requires_large_context
priority
timeout
repository/base/paths/acceptance
```

No ATHBA stage or execution-form field appears.

### Compatibility

- old `rack-ai/work-unit/v1` remains readable;
- old `capability=implementation` maps to the legacy coding route;
- new request is versioned or additive;
- old packets remain readable;
- no selection behavior changes until Phase 3.

### Source priority admission

Add a generic source policy equivalent to:

```text
source_system = athba
max_priority = medium
```

Rack AI rejects ATHBA high/paramount requests.

This is generic admission policy, not software-engineering knowledge.

### Tests

- capability-set round trip;
- exact capability vocabulary;
- exact global priority vocabulary;
- multi-capability request;
- unknown capability/priority fail closed;
- ATHBA low/medium accepted;
- ATHBA high/paramount rejected;
- opaque IDs and idempotency;
- no ATHBA work kind on wire;
- no execution-form field;
- old request/packet compatibility.

## Phase 3 — Rack AI generic capability selection

### Repository

Rack AI, stacked after trusted execution/provenance foundations.

### Goal

Extend model/worker registry with:

```text
capabilities
qualified complexity envelope
large-context eligibility
qualification status/evidence
profile version
```

Keep model profile, runtime instance, and physical resource separate.

Current deployment configuration:

```text
Qwen profile
  capabilities: [coding]

Gemma profile
  capabilities: [reasoning, coding]
```

Add deterministic selection:

1. filter by all hard capabilities;
2. filter by complexity/context/qualification;
3. filter by health/resource/admission;
4. rank by least-scarce sufficient profile, availability, warm state, throughput, queue age, priority, deterministic tie-break.

Add `SelectionDecision` linked to `WorkerExecutionProvenance`.

### Non-goals

- no ATHBA semantics;
- no shared dependency queue;
- no adaptive learning;
- no ComfyUI arbitration;
- no preemption;
- no tool-profile change.

### Tests

- reasoning+coding excludes coding-only worker;
- coding/small prefers coding-only worker;
- no eligible worker fails closed;
- priority never upgrades capability;
- ATHBA priority ceiling enforced;
- selected worker matches execution provenance;
- mismatch fails closed;
- old registry remains readable.

### Sequential Rack AI qualification

Run one request at a time:

1. reasoning+coding/medium/medium -> stronger worker;
2. coding/small/medium -> coding worker;
3. reasoning+coding/medium/medium -> stronger worker.

Do not run an ATHBA feature yet.

## Phase 4 — Primary-capable scenario authoring

### Repository

ATHBA.

### Goal

Map complete scenario authoring and repair to:

```text
capabilities: [reasoning, coding]
complexity: medium
priority: medium
```

Under current Rack AI configuration this selects a Gemma/local-primary runtime without ATHBA naming it.

Retain:

- strict structural validation;
- independent intent review;
- exact candidate repair lineage;
- no-candidate fresh retries;
- four actual submissions;
- no fifth attempt;
- scenario remains planning material;
- deterministic adapter unchanged.

### Live gate

A fresh neutral scenario is authored, approved, and decomposed. Stop before full feature implementation only for this focused gate.

## Phase 5 — Coding-first frontier route and stronger fallback

### Repository

ATHBA, using Rack AI Phase 3.

### Goal

Normal frontier profile:

```text
[coding], small, low-or-medium priority
```

After four genuine ATHBA-counted model failures:

```text
[reasoning, coding], medium, medium priority
```

Preserve:

- stable work ID;
- unique submission IDs;
- exact frontier;
- base ref/SHA;
- allowed paths;
- accepted tests;
- candidate/no-candidate history;
- tier counters;
- restart state.

No coder-primary-coder bounce. No fifth attempt in either tier.

### Tests

- coding tier selects coding worker;
- four model-originated failures authorize one stronger profile;
- infrastructure failures do not consume tier attempts;
- stronger profile selects reasoning+coding worker;
- objective/base/paths/tests remain immutable;
- process restart preserves tier and counters;
- deterministic acceptance remains authoritative;
- both tiers exhausted -> capability blocked.

## Phase 6 — Sequential tiny feature proof

One external work unit at a time.

Required:

1. primary-capable complete scenario;
2. independent intent approval;
3. deterministic fragments/frontiers;
4. coding-worker frontier implementation;
5. deterministic GREEN/regression/promotion;
6. stronger fallback proof, forced through deterministic test configuration or naturally occurring without fixture-specific prompt changes;
7. checkpoint/new-process resume;
8. behavior review;
9. final reconciliation;
10. final tests pass.

No concurrency or resource preemption is part of this gate.

## Phase 7 — Fresh ReservationBook proof

Only after Phase 6 passes:

- fresh project;
- independent Behavior Planner and Gatekeeper;
- primary-capable scenario authoring;
- strict frontiers;
- coding-first implementation and stronger fallback;
- deterministic regression and trusted revisions;
- restart proof;
- final Gatekeeper YES/NO reconciliation;
- no feature-specific harness changes.

## Deferred Rack AI scheduling specification

After the sequential proofs:

- three-GPU placement;
- identical Gemma runtimes on 4060 Ti/4080 Super;
- model residency and switching cost;
- high/paramount workload admission;
- ComfyUI/image/video/audio leases;
- draining or preempting low/medium ATHBA jobs;
- idle-capacity overflow;
- fairness and queue ageing;
- multi-project throughput.

None is a PR23 merge gate.

## Validation matrix

### ATHBA

- profile resolver mappings;
- priority type restriction;
- connector high/paramount rejection;
- port replaceability;
- tier and attempt persistence;
- no concrete worker IDs;
- deterministic PR23 behavior unchanged.

### Rack AI

- schema compatibility;
- capability registry;
- source priority policy;
- selection decisions;
- selection/provenance consistency;
- current bounded workspace executor regression.

### Cross-repository

- generic request round trip;
- low/medium ATHBA priority only;
- reasoning+coding selection;
- coding-only selection;
- stronger generic selection;
- opaque identity correlation;
- no semantic leakage.

## Rollback boundaries

Each phase is isolated:

- Phase 1: ATHBA abstraction only;
- Phase 2: additive wire contract;
- Phase 3: selector/registry behind compatibility;
- Phase 4: scenario profile mapping;
- Phase 5: tier routing;
- proofs add evidence only.

## Stop conditions

- no `execution_form` field for PR23;
- no ATHBA high/paramount priority;
- no software-engineering fields in Rack AI;
- no concurrency implementation before sequential proof;
- no tool/test-grammar accommodation;
- no fifth attempt;
- no ReservationBook before tiny proof;
- both tiers failing tiny feature triggers architecture simplification review.

## Completion markers

```text
ATHBA_WORKSPACE_PORT = PASS
ATHBA_PRIORITY_MAXIMUM = MEDIUM
GENERIC_CAPABILITY_CONTRACT = PASS
RACK_AI_SOURCE_PRIORITY_POLICY = PASS
RACK_AI_CAPABILITY_SELECTION = PASS
PRIMARY_CAPABLE_SCENARIO_AUTHORING = PASS
CODING_FIRST_FRONTIER_ROUTE = PASS
BOUNDED_STRONGER_FALLBACK = PASS
TINY_SEQUENTIAL_PROOF = PASS
RESERVATIONBOOK_PROOF = PASS
```