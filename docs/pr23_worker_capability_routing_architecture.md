# PR23 ATHBA Routing Through a Generic Rack AI Workspace Connector

## Status

**Documentation-only revised architecture.** No runtime, test, configuration, Rack AI, JCode, model-service, or generated-state code is changed here.

This proposal is stacked on the implemented PR23 strict-TDD foundation at `624c666467b48fcfad72d5f0b5bfdaff6558bd97`.

PR23 remains open because the strict-TDD machinery has not yet completed a real feature end to end. The purpose of this design is to assign model work to suitable generic model capabilities without teaching Rack AI software engineering.

## Explicit design position

The corrected boundary is:

> ATHBA owns every software-engineering concept. Rack AI owns generic AI execution, worker/model/resource selection, queueing, leases, and evidence.

I agree with this boundary. Rack AI must not receive or understand scenario authoring, scenario repair, Tester, Developer, RED, GREEN, frontier, regression repair, behavior review, Gatekeeper stage, or ATHBA dependency meaning.

ATHBA may use all of those concepts internally. An ATHBA-owned connector translates only ready work into a small generic request.

## What Rack AI actually supports today

The current Rack AI `rack-ai/work-unit/v1` path is an MVP application-development contract. It currently understands:

```text
workload.kind = application-development
requirements.capability = implementation
requirements.complexity = small | medium | large
requirements.requires_large_context = true | false
```

The current selector uses `small` work to prefer the minimal implementer and uses medium/large or large-context work to prefer the stronger non-minimal worker.

There is **not** currently an implemented generic enum containing:

```text
structured_response
workspace_change
media_artifact
```

The present work-unit path has one implicit operation: a bounded repository/workspace change. Rack AI translates the request into its existing trusted change executor, prepares a worktree, invokes JCode, enforces paths and limits, runs acceptance, and returns a candidate revision and evidence.

The earlier PR27 wording made proposed future execution forms sound like an existing Rack AI feature. That was incorrect.

## Execution operation versus routing metadata

Rack AI necessarily knows which generic operation it is performing because different operations require different executors and result contracts. That does **not** mean an `execution_form` field must be added to the PR23 routing header.

For version 1 of this design:

- the connector method or Rack AI endpoint identifies the operation;
- PR23 uses only the existing bounded **workspace-change** operation;
- routing metadata selects a suitable model/worker within that operation;
- pure reasoning calls continue through ATHBA's existing `ReasoningGateway` during this phase;
- visual, audio, media-pipeline, and generic structured-inference operations belong to a separate Rack AI specification.

Conceptually:

```text
AiWorkspaceExecutionPort.submit_workspace_change(request)
```

rather than:

```text
submit(request with execution_form = workspace_change)
```

This is simpler, more type-safe, and avoids pretending that Rack AI already implements execution modes it does not have.

## Core architecture

```text
ATHBA software-development state
  -> ATHBA decides which work is semantically ready
  -> ATHBA internal execution-profile resolver
  -> backend-neutral workspace execution port
  -> RackAiWorkspaceConnector
  -> generic bounded workspace job
  -> Rack AI selects model/worker/resource
  -> Rack AI executes and returns generic evidence
  -> connector translates the result
  -> ATHBA interprets it using software-development semantics
```

A future alternative backend can implement the same workspace port without changing ATHBA's strict-TDD domain.

## Responsibility boundary

### ATHBA owns

- requirements, behaviors, and acceptance meaning;
- internal software-development stages;
- semantic readiness and dependencies;
- strict-TDD phase and frontier progression;
- internal model-work classification;
- internal mapping to generic model requirements;
- model-attempt and escalation policy;
- candidate interpretation and repair feedback;
- trusted revision progression;
- final Specification Gatekeeper reconciliation.

### Rack AI owns

- generic model capability registration;
- worker/model/runtime/resource availability;
- concrete worker and GPU selection;
- generic queue ordering;
- resource leases;
- harness/runtime configuration;
- trusted worktree execution;
- path, network, process, timeout, and resource enforcement;
- selection evidence and execution provenance;
- terminal execution packets.

### Rack AI explicitly does not own

- ATHBA work kinds;
- behavior readiness;
- project dependency graphs;
- Tester or Developer identity;
- scenario or frontier semantics;
- RED/GREEN meaning;
- repair or review policy;
- escalation meaning;
- semantic acceptance.

## Generic routing header

For the bounded workspace operation, ATHBA sends a deliberately small generic routing header.

### Model capabilities

Version 1 defines broad model-type capabilities:

```text
reasoning
coding
visual
audio
```

The field is a non-empty set because a model or job may combine capabilities:

```text
[coding]
[reasoning]
[reasoning, coding]
[visual]
[audio]
```

These are model classes, not software-engineering skills. New broad model classes may be added through a versioned contract later.

### Complexity

```text
small
medium
large
```

Complexity is a generic size/difficulty envelope. It is independent of semantic readiness and priority.

### Context requirement

```text
requires_large_context = true | false
```

Rack AI filters against registered model context capacity.

### Global Rack AI priority vocabulary

Rack AI's global queue may use:

```text
low
medium
high
paramount
```

The values exist for rack-wide arbitration among unrelated source systems and workloads.

### ATHBA priority ceiling

ATHBA may emit only:

```text
low
medium
```

It must never emit `high` or `paramount`.

Reason:

- ATHBA is continuous slow-burn background development;
- there will normally be more ATHBA work available than immediate capacity;
- interactive or time-sensitive rack workloads must be able to outrank and reclaim resources from ATHBA;
- high and paramount are reserved for other authorized source systems, operator policy, urgent interactive workloads, service restoration, or safety-critical control.

The boundary is enforced twice:

1. `RackAiWorkspaceConnector` rejects an ATHBA request above `medium` before transport.
2. Rack AI source/admission policy records `source_system = athba` with `max_priority = medium` and rejects a forged or buggy higher-priority request.

Rack AI may later drain or preempt ATHBA capacity because a higher-priority job arrived. It must not rewrite an ATHBA request's priority upward.

### Opaque identity and safety constraints

The request also carries generic data needed for execution:

- source-system identity;
- stable opaque `work_id`;
- unique `submission_id`;
- idempotency key;
- timeout;
- objective;
- repository/base binding;
- allowed paths;
- deterministic acceptance commands/artifacts;
- network and process constraints;
- evidence references.

Rack AI treats the IDs as opaque. It does not infer ATHBA ordering or dependencies from them.

## Current worker/model mapping

Current names are deployment configuration, never ATHBA semantic constants.

### Qwen local-coder profile

```text
capabilities: [coding]
qualified envelope: small bounded coding work
large context: no
current resource: RTX 2060
qualification: qualified_with_constraints
```

### Gemma local-primary profile

```text
capabilities: [reasoning, coding]
qualified envelope: medium/large within measured limits
large context: yes
current resource: RTX 4060 Ti
qualification: qualified
```

### Future 4080 Super runtime

A second runtime using the same Gemma model/profile on the RTX 4080 Super exposes the same intelligence capabilities:

```text
[reasoning, coding]
```

It may differ in throughput, model-residency state, and availability. Rack AI may select it for performance. ATHBA sees no different semantic intelligence merely because the GPU is faster.

## Generic selection

### Hard eligibility

A worker is eligible only when:

1. it supports every required capability;
2. its qualification envelope covers the requested complexity;
3. its context capacity satisfies the request;
4. its runtime and resource are healthy and queueable;
5. the bounded workspace contract can be enforced;
6. source admission policy accepts the request and priority.

### Ranking among eligible workers

Rack AI ranks eligible workers using generic resource policy, such as:

- least-scarce sufficient capability set;
- current availability and lease state;
- warm/resident model preference;
- measured throughput;
- expected completion time;
- queue age;
- requested global priority;
- deterministic tie-break.

For `[coding]`, `small`, a coding-only worker is normally the least-scarce sufficient choice. For `[reasoning, coding]`, a coding-only worker is ineligible.

## ATHBA internal mapping

ATHBA keeps a process-routing catalogue. Only the generic right-hand side crosses the connector.

| ATHBA internal stage | Execution surface | Generic capability | Complexity | ATHBA priority |
| --- | --- | --- | --- | --- |
| Behavior planning | ATHBA ReasoningGateway | reasoning | medium/large | medium |
| Independent Gatekeeper atomization | ATHBA ReasoningGateway | reasoning | medium/large | medium |
| Complete scenario authoring | Rack AI workspace connector | reasoning + coding | medium | medium |
| Scenario repair | Rack AI workspace connector | reasoning + coding | medium | medium |
| Scenario intent review | ATHBA ReasoningGateway | reasoning | medium | medium |
| Frontier decomposition | deterministic ATHBA adapter | none | n/a | n/a |
| RED validation | deterministic ATHBA execution | none | n/a | n/a |
| Active-frontier implementation | Rack AI workspace connector | coding | small | low/medium |
| Stronger frontier fallback | Rack AI workspace connector | reasoning + coding | medium | medium |
| Focused GREEN/regression | deterministic ATHBA execution | none | n/a | n/a |
| Senior review | ATHBA ReasoningGateway | reasoning | medium | medium |
| Semantic behavior repair | Rack AI workspace connector | reasoning + coding | medium/large | medium |
| Final reconciliation | ATHBA ReasoningGateway | reasoning | large | medium |

ATHBA may use richer internal ordering, but the outbound priority is always clamped to `low` or `medium`.

## No shared semantic pool

ATHBA owns one authoritative semantic work ledger.

ATHBA:

- retains dependencies and readiness;
- withholds blocked work;
- applies one-project mutation rules;
- submits every currently dispatchable ready item once;
- correlates generic terminal results;
- unlocks subsequent work.

Rack AI receives only ready generic jobs and owns:

- generic queueing;
- source priority policy;
- worker/model/resource selection;
- leases;
- execution;
- status and terminal evidence.

Rack AI does not sequence ATHBA dependencies. A sequence number may be retained for audit but is not an execution dependency.

## Attempt and stronger-route policy

ATHBA owns tier meaning.

For narrow implementation:

```text
Tier 1 request
  capabilities: [coding]
  complexity: small
  priority: low or medium
  maximum actual model submissions: 4

Tier 2 after ATHBA proves Tier-1 exhaustion
  capabilities: [reasoning, coding]
  complexity: medium
  priority: medium
  maximum actual model submissions: 4
```

Rack AI sees two generic workspace submissions linked by opaque IDs. It does not know that this is a TDD fallback.

There is no fifth attempt within a tier and no automatic return from the stronger tier to the coding-only tier.

## Significance of the Rack AI change

The required PR23 Rack AI change is meaningful but bounded. It is not a scheduler rewrite.

Required:

1. preserve `rack-ai/work-unit/v1` compatibility;
2. add a versioned generic workspace request or additive compatibility shape;
3. replace/extend singular `implementation` with a capability set: reasoning, coding, visual, audio;
4. retain small/medium/large complexity;
5. retain `requires_large_context`;
6. add global low/medium/high/paramount priority;
7. enforce ATHBA's source priority ceiling of medium;
8. add generic capability/qualification metadata to model profiles;
9. select using generic eligibility and ranking;
10. return a selection decision linked to existing execution provenance.

Not required for PR23:

- ATHBA work kinds in Rack AI;
- shared dependency pools;
- visual/audio executors;
- generic structured-response execution;
- ComfyUI arbitration;
- three-GPU optimization;
- preemption;
- idle-primary overflow;
- adaptive scheduling.

The trusted workspace-change executor, JCode path, worktree handling, path policy, acceptance, timeout, and terminal packet machinery remain intact.

## Sequential proof before concurrency

The first gates are sequential:

1. `[reasoning, coding]`, medium selects a suitable stronger worker.
2. `[coding]`, small selects the least-scarce sufficient coding worker.
3. after simulated/real tier exhaustion, `[reasoning, coding]`, medium selects the stronger worker.
4. selection evidence matches execution provenance.
5. one tiny ATHBA feature completes sequentially.
6. ReservationBook completes sequentially.
7. only then design/test multi-GPU concurrency, ComfyUI drain, priority preemption, and idle capacity.

## Future rack-wide scheduling

A separate Rack AI specification will define:

- 2060, 4060 Ti, and 4080 Super runtime placement;
- identical model profiles on multiple GPUs;
- model residency and switching cost;
- ComfyUI/image/video/audio leases;
- high/paramount workload admission;
- draining or preemption of low/medium ATHBA leases;
- fairness and queue ageing;
- multi-project throughput.

That work must preserve this generic connector boundary.

## Stop conditions

- No software-engineering terms cross into Rack AI.
- No explicit generic execution-form enum is added for PR23.
- No tool or test grammar changes are justified by one model output.
- ATHBA never emits high or paramount priority.
- No fifth model submission exists within either ATHBA tier.
- No shared ATHBA/Rack AI dependency pool exists.
- No concurrency optimization precedes sequential routing proof.
- If both model tiers cannot complete the same tiny feature under the frozen generic contract, PR23 stops for architecture simplification review.

## Definition of done

The routing design is complete when:

- ATHBA maps internal stages to generic model capabilities without exposing stage names;
- the connector is replaceable;
- PR23 uses only the bounded workspace-change operation;
- Rack AI selects concrete workers from generic capabilities and resource state;
- ATHBA priority is constrained to low/medium;
- selection evidence and execution provenance agree;
- stronger scenario authoring, deterministic decomposition, coding-first frontier implementation, and bounded stronger fallback are proven sequentially;
- a fresh tiny feature and ReservationBook complete without fixture-specific harness changes.