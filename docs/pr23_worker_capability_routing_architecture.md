# PR23 ATHBA Routing and Generic Rack AI Connector Architecture

## Status

**Documentation-only revised proposal.** No runtime, test, configuration, Rack AI, JCode, model-service, or generated-state code is changed by this document.

This proposal is stacked on the implemented PR23 strict-TDD microcycle foundation at `624c666467b48fcfad72d5f0b5bfdaff6558bd97`.

PR23 remains open and incomplete because no real feature has yet completed the full route through scenario authoring, deterministic frontier progression, Developer GREEN, regression, restart, behavior review, and final Specification Gatekeeper reconciliation.

## Correction to the first PR27 draft

The first PR27 draft allowed software-development terms such as `scenario_authoring`, `frontier_implementation`, required semantic capabilities, and escalation tier to cross into Rack AI.

That boundary was too broad.

The revised decision is:

> ATHBA owns every software-engineering concept. Rack AI receives only a generic executable AI job described through model-oriented capabilities and generic scheduling constraints.

Rack AI must not understand scenarios, RED, GREEN, frontiers, Tester, Developer, behavior review, regression repair, or Gatekeeper reconciliation.

ATHBA may use those concepts internally, but an ATHBA-owned connector translates them into the smaller generic Rack AI contract.

## Core architecture

```text
ATHBA software-development state
  -> ATHBA internal work classification
  -> ATHBA execution-profile resolver
  -> polymorphic AI execution port
  -> Rack AI connector
  -> generic Rack AI job
  -> Rack AI selects model/worker/resource
  -> generic terminal result and evidence
  -> connector maps evidence back
  -> ATHBA interprets it using software-development semantics
```

The connector is an anti-corruption layer. A future alternative rack backend can replace Rack AI by implementing the same ATHBA execution port without changing ATHBA's TDD domain.

## Change-control invariant

Any further harness change must demonstrate that it restores the original generic contract rather than merely allowing a live proof to move one step forward.

Model output that violates an existing documented contract is not, by itself, evidence that the harness must change.

From this point:

- strict scenario grammar remains frozen;
- deterministic frontier decomposition remains frozen;
- the four-submission limit within a model tier remains frozen;
- typed execution budgets remain frozen unless independent operational evidence justifies a generic revision;
- no tool is added merely because a model attempted to call it;
- no unsupported test form is accepted merely because a model generated it;
- bounded worker routing replaces further fixture-specific accommodation.

## Responsibility boundary

### ATHBA owns

- requirements, behaviors, and acceptance meaning;
- internal development stages and work kinds;
- semantic readiness and dependency progression;
- TDD phase and strict frontier progression;
- whether work is deterministic or model-executed;
- internal mapping from a development stage to a generic execution profile;
- model-attempt accounting at the development level;
- candidate interpretation and repair evidence;
- escalation authorization;
- trusted revision progression;
- final Specification Gatekeeper reconciliation.

### Rack AI owns

- generic model capability registration;
- model/worker/runtime/resource availability;
- concrete worker and GPU selection;
- resource leases and generic queue scheduling;
- harness and model-runtime configuration;
- trusted workspace execution;
- generic path, network, process, timeout, and resource enforcement;
- selection evidence and execution provenance;
- terminal execution packets.

### Rack AI explicitly does not own

- scenario authoring semantics;
- scenario repair semantics;
- Tester or Developer roles;
- RED/GREEN meaning;
- frontier ordering;
- behavior readiness;
- project dependency graphs;
- semantic repair decisions;
- Specification Gatekeeper meaning.

## ATHBA internal work model

ATHBA retains an internal typed taxonomy because it must know what stage of software development it is performing.

Examples include:

- behavior planning;
- Gatekeeper atomization;
- complete scenario authoring;
- scenario intent review;
- scenario repair;
- deterministic frontier decomposition;
- RED validation;
- narrow frontier implementation;
- mechanical implementation repair;
- deterministic focused GREEN;
- deterministic accumulated regression;
- regression repair;
- senior behavior review;
- semantic behavior repair;
- final Gatekeeper reconciliation.

These names remain entirely inside ATHBA.

An ATHBA execution-profile resolver maps each model-executed stage to generic model and scheduling requirements. Deterministic stages do not leave ATHBA.

## Generic Rack AI routing contract

Rack AI receives a deliberately small routing header.

### Generic model capabilities

The version-1 capability vocabulary is aligned with broad classes of model:

- `reasoning`
- `coding`
- `visual`
- `audio`

A job may require one or more capabilities.

Examples:

```text
[reasoning]
[coding]
[reasoning, coding]
[visual]
[audio]
```

Unknown required capabilities fail closed under a versioned contract. New broad model classes may be added later without teaching Rack AI software-engineering terminology.

### Complexity

```text
small
medium
large
```

Complexity describes the size/difficulty envelope of the generic model job. It is not a TDD phase and does not determine semantic readiness.

### Context requirement

```text
requires_large_context = true | false
```

This remains a generic routing constraint. Rack AI knows the context capacity of registered model profiles and filters accordingly.

### Priority

```text
low
medium
high
paramount
```

Priority determines queue ordering, not intelligence or semantic state.

- `low`: background or non-blocking work;
- `medium`: normal ready work;
- `high`: work currently blocking an approved critical path;
- `paramount`: rare operator- or safety-authorized work that must outrank ordinary jobs.

Routine ATHBA stages must not all default to `paramount`.

### Generic execution form

Rack AI may also need a generic execution form so it knows how to run the job, for example:

- `structured_response`
- `workspace_change`
- `media_artifact`

This describes the transport/output shape. It does not reveal software-development meaning.

### Identity and execution constraints

The generic request also carries opaque and safety-critical data such as:

- `work_id` — stable identity of the logical ATHBA work;
- `submission_id` — unique identity of one actual execution attempt;
- idempotency key;
- execution budget;
- payload or objective;
- repository/base/allowed paths for a workspace job;
- expected response schema or acceptance commands;
- evidence references.

Rack AI treats `work_id` and `submission_id` as opaque identifiers. It does not infer dependencies or development sequence from them.

## Target generic request

Conceptually:

```text
GenericAiJobRequest
  version
  source_system
  work_id
  submission_id
  idempotency_key
  capabilities[]
  complexity
  requires_large_context
  priority
  execution_form
  timeout_seconds
  input
  execution_constraints
  output_contract
  evidence_refs
```

The exact wire format is a later cross-repository contract. The semantic boundary above is authoritative.

## Current deployment mapping

Current deployment names are configuration evidence in Rack AI, never ATHBA domain constants.

### Current small coding worker

```text
model profile: Qwen3.5 / eqaq-v2
worker: local-coder
resource: RTX 2060
capabilities: coding
qualified complexity: small bounded coding work
large-context eligible: no
qualification: qualified_with_constraints
```

### Current stronger worker

```text
model profile: Gemma primary profile
worker: local-primary
resource: RTX 4060 Ti
capabilities: reasoning, coding
qualified complexity: medium/large within measured envelope
large-context eligible: yes
qualification: qualified
```

### Future 4080 Super worker

A future worker running the same Gemma model/runtime profile on the RTX 4080 Super has the same intelligence capabilities as the 4060 Ti worker:

```text
capabilities: reasoning, coding
qualification envelope: same model profile
```

Its throughput, load time, and availability may differ. Rack AI may prefer it because it is faster or already resident, but ATHBA sees no new semantic capability merely because the GPU is faster.

## Generic eligibility and ranking

Rack AI selection should be generic and deterministic.

### Hard eligibility filters

A worker is eligible only when:

1. every requested capability is supported;
2. the worker/model is qualified for the requested complexity;
3. the large-context requirement is satisfied;
4. the worker, model, harness, and resource are healthy and available or queueable;
5. execution constraints can be enforced.

### Ranking among eligible workers

Rack AI may rank eligible workers using generic resource policy such as:

- priority and queue age;
- least-scarce sufficient capability profile;
- warm/resident model preference;
- measured throughput;
- expected completion time;
- current lease and resource pressure;
- deterministic tie-break.

For a `coding`-only small job, a coding-only worker is normally less scarce than a worker that also provides reasoning. This naturally preserves the stronger reasoning worker without Rack AI knowing the job is a frontier.

For a `[reasoning, coding]` job, a coding-only worker is ineligible.

## ATHBA mapping examples

These mappings are internal ATHBA policy implemented before the connector boundary.

### Complete behavioral scenario

ATHBA knows this is scenario authoring. The connector emits:

```text
capabilities: [reasoning, coding]
complexity: medium
requires_large_context: false by default, true only when the actual context requires it
priority: high when it blocks the active behavior
execution_form: workspace_change
```

Under the current Rack AI registry, the coding-only Qwen worker is ineligible and a reasoning-plus-coding worker is selected.

Rack AI never receives the phrase `scenario_authoring`.

### Narrow frontier implementation

ATHBA knows this is an active frontier implementation. The connector emits:

```text
capabilities: [coding]
complexity: small
requires_large_context: false
priority: medium or high according to ATHBA critical-path policy
execution_form: workspace_change
```

Both current primary and coder may support coding, but generic least-scarce-sufficient ranking normally selects the coding-only worker.

Rack AI never receives the phrase `frontier_implementation`.

### Stronger fallback for the same frontier

After ATHBA proves the narrow tier exhausted, it retains the same `work_id` and creates a new `submission_id` with a stronger generic profile:

```text
capabilities: [reasoning, coding]
complexity: medium
requires_large_context: false unless evidence says otherwise
priority: high
execution_form: workspace_change
```

This makes the coding-only worker ineligible without telling Rack AI that this is a TDD escalation.

## Replaceable connector

ATHBA defines a polymorphic execution port conceptually equivalent to:

```text
AiExecutionPort
  submit(GenericAiJobRequest) -> SubmissionAcknowledgement
  get_status(submission_id) -> GenericJobStatus
  get_result(submission_id) -> GenericAiJobResult
  cancel(submission_id) -> CancellationResult
```

Implementations may include:

- `RackAiConnector`;
- deterministic fake connector for tests;
- a future alternative rack/backend connector.

The ATHBA TDD engine depends on the port, not directly on Rack AI's JSON or CLI.

A separate ATHBA-owned mapper performs:

```text
ATHBA internal work
  -> generic execution profile
  -> GenericAiJobRequest
```

The Rack AI connector performs only transport, serialization, correlation, and generic result translation.

## No shared semantic pool

ATHBA and Rack AI do not share one queue or one authoritative pool.

### ATHBA semantic work ledger

ATHBA owns:

- dependency graph;
- behavioral state;
- readiness;
- TDD phase;
- project mutation safety;
- attempt/escalation state;
- trusted base and acceptance meaning.

ATHBA submits only work it has already determined is ready.

It should submit every currently dispatchable item, subject to its own project-mutation and idempotency rules, rather than expose its internal dependency graph to Rack AI.

### Rack AI generic job queue

Rack AI receives ready generic jobs and owns:

- queue ordering by generic priority;
- worker/model/resource eligibility;
- leases;
- execution;
- status and terminal evidence.

Rack AI does not decide that job B must precede job A. ATHBA submits A only after B has completed when that dependency exists.

A monotonically increasing submission sequence may be retained for audit, but Rack AI must not treat it as a semantic dependency mechanism.

## Queue interaction

```text
ATHBA pending work
  -> dependencies and state resolved internally
  -> ATHBA ready and undispatched
  -> connector submits generic job once
  -> Rack AI acknowledges and queues it
  -> Rack AI selects and executes when capacity exists
  -> terminal result correlated by submission_id
  -> ATHBA interprets result
  -> ATHBA unlocks or creates further ready work
```

Temporary resource unavailability leaves a submitted job queued in Rack AI. Permanent lack of any eligible capability returns a generic capability-unavailable blocker.

## Attempt and escalation ownership

ATHBA owns model-attempt policy because only ATHBA knows whether a result is a candidate defect, semantic repair, or another development outcome.

Rack AI records each actual invocation and terminal result.

For narrow implementation, version 1 remains:

```text
Tier 1
  generic request: [coding], small
  maximum actual submissions: 4

Tier 2 after proven Tier-1 exhaustion
  generic request: [reasoning, coding], medium
  maximum actual submissions: 4
```

These are two explicit ATHBA tiers, not eight anonymous retries.

Rack AI sees independent generic submissions linked by opaque `work_id`; it does not own the reason for escalation.

There is no automatic return from Tier 2 to Tier 1.

## Dynamic GPUs and competing workloads

Detailed three-GPU scheduling, ComfyUI leases, model residency, and workload switching belong to a separate Rack AI architecture discussion.

This boundary already supports that future design:

- model capability belongs to a model profile;
- an executable worker is one runtime instance of that profile;
- a physical GPU is a resource leased by Rack AI;
- two workers running the same model on different GPUs expose the same semantic capabilities but different throughput/availability;
- when ComfyUI leases one GPU, the corresponding worker becomes unavailable while other eligible workers continue or queued jobs wait;
- ATHBA's work descriptors do not change.

## Sequential proof before concurrency

The first acceptance gate is routing correctness, not multi-GPU optimization.

Required sequential proof order:

1. a `[reasoning, coding]` request selects a suitable stronger worker;
2. a `[coding]` small request selects the coding worker under least-scarce-sufficient ranking;
3. a stronger fallback request for the same opaque work selects a reasoning-plus-coding worker;
4. selection evidence matches execution provenance;
5. one tiny ATHBA feature completes sequentially;
6. only then test concurrent workers, idle overflow, dynamic GPU loss, or ComfyUI switching.

## Version-1 scope required for PR23

1. ATHBA internal work-to-profile mapping.
2. Polymorphic AI execution port and Rack AI connector.
3. Generic Rack AI capability set: reasoning, coding, visual, audio.
4. Complexity: small, medium, large.
5. `requires_large_context` boolean.
6. Priority: low, medium, high, paramount.
7. Generic worker/model capability registration and deterministic selection.
8. Selection evidence linked to execution provenance.
9. Primary-capable complete scenario authoring through `[reasoning, coding]`.
10. Deterministic frontier decomposition unchanged.
11. Coding-only preferred narrow implementation.
12. Stronger `[reasoning, coding]` fallback after four narrow-tier failures.
13. Persistence/resume of work, submissions, tiers, and candidate lineage.
14. Fresh sequential tiny-feature proof.
15. Fresh ReservationBook proof and final Gatekeeper reconciliation.

## Deferred to the Rack AI scheduling specification

- three-GPU placement policy;
- model residency and warm-start optimization;
- ComfyUI/image/video/audio lease arbitration;
- idle stronger-worker overflow;
- queue ageing refinements;
- throughput forecasting;
- preemption;
- cross-project fairness;
- adaptive success-rate routing.

Those features must use the same generic boundary and must not introduce ATHBA software-development semantics into Rack AI.

## Stop conditions

- No Rack AI software-engineering work kinds.
- No scenario, Tester, Developer, RED, GREEN, frontier, or Gatekeeper terms in the Rack AI routing contract.
- No shared semantic queue.
- No dependency scheduling delegated to Rack AI.
- No tool or test-grammar change justified by one model output.
- No fifth submission within a tier.
- No coder-primary-coder bounce.
- No concurrency implementation before sequential routing works.
- No ReservationBook proof before the tiny routing proof.
- If both generic tiers fail the same tiny feature under the frozen contract, PR23 stops for architecture simplification review rather than adding another fixture-driven subsystem.

## Definition of done

The routing architecture is complete when:

- ATHBA retains all software-development meaning;
- ATHBA maps internal work to a small generic AI execution profile;
- the connector is replaceable;
- Rack AI receives only generic capabilities, complexity, context, priority, execution form, identity, and execution constraints;
- Rack AI selects and evidences the concrete model/worker/resource;
- complete scenario authoring reaches a reasoning-plus-coding worker;
- deterministic adapters derive strict frontiers;
- narrow implementation normally reaches a coding worker;
- stronger fallback is bounded and preserves immutable work state;
- sequential routing completes one tiny feature;
- a fresh ReservationBook build completes or reaches a legitimate capability/human blocker without feature-specific harness changes;
- every Gatekeeper item receives final accepted-test YES/NO reconciliation.
