# PR23 Generic Rack AI Connector Contract

## Status

Documentation-only connector proposal.

This document defines the anti-corruption layer between ATHBA's software-development domain and a generic AI rack/backend. Rack AI is the first implementation target, but ATHBA must remain portable to a different backend connector.

## Design goal

ATHBA must be able to say:

```text
I have a ready job requiring reasoning and coding,
with medium complexity,
normal context,
high priority,
and a bounded workspace-change contract.
```

It must not have to say:

```text
Use local-primary on the 4060 Ti because this is scenario authoring.
```

Rack AI must be able to schedule the generic job without knowing what a scenario, frontier, Tester, Developer, RED, GREEN, or Gatekeeper is.

## Layering

```text
ATHBA domain
  internal stages, dependencies, TDD state, attempts, revisions

ATHBA ExecutionProfileResolver
  maps an internal stage to generic model/scheduling parameters

AiExecutionPort
  backend-neutral submission/status/result contract

RackAiConnector
  serializes generic requests and translates generic results

Rack AI
  generic capability registry, queue, worker/resource selection, execution
```

The execution-profile resolver and connector are separate responsibilities:

- the resolver knows ATHBA stages but not Rack AI transport;
- the connector knows Rack AI transport but not ATHBA stage semantics.

## Generic capability vocabulary

Version 1 defines four broad model capability classes:

```text
reasoning
coding
visual
audio
```

The field is a non-empty set because one job may require multiple broad capabilities.

Examples:

```text
[reasoning]
[coding]
[reasoning, coding]
[visual]
[audio]
```

Rules:

- capability names are generic model classes;
- unknown required capabilities fail closed;
- no ATHBA stage name is a capability;
- no model or GPU identifier is a capability;
- capability expansion requires a versioned cross-repository contract;
- detailed software skills remain ATHBA internal;
- measured worker qualification remains Rack AI configuration/evidence.

## Generic scheduling parameters

### Complexity

```text
small
medium
large
```

Complexity is a generic difficulty/size envelope used against a worker/model's qualified capability envelope.

### Large-context requirement

```text
requires_large_context: bool
```

Rack AI determines which registered model profiles satisfy the large-context class.

### Priority

```text
low
medium
high
paramount
```

Priority is queue order only.

It must never be used as an implicit capability upgrade.

### Execution form

```text
structured_response
workspace_change
media_artifact
```

Execution form tells the backend what kind of output/containment contract is required. It does not reveal software-development stage.

## Boundary request

Conceptual typed request:

```text
GenericAiJobRequest
  version
  source_system
  work_id
  submission_id
  idempotency_key
  capabilities: set[GenericCapability]
  complexity: GenericComplexity
  requires_large_context: bool
  priority: GenericPriority
  execution_form: GenericExecutionForm
  timeout_seconds: int
  input: GenericJobInput
  constraints: GenericExecutionConstraints
  output_contract: GenericOutputContract
  evidence_refs: list[str]
```

### Identity

`work_id`

- stable across model attempts and ATHBA capability tiers;
- opaque to Rack AI;
- never reused for different semantic work.

`submission_id`

- unique for every actual backend submission;
- survives connector retries and process restart;
- used to correlate acknowledgements, status, and terminal result.

`idempotency_key`

- prevents duplicate execution of the same submission;
- is not a dependency or sequence mechanism.

A monotonic `submission_sequence` may be included for audit, but Rack AI must not infer semantic ordering from it.

## Generic job input

The connector supports generic forms without leaking ATHBA stage names.

### Structured response input

```text
GenericStructuredInput
  prompt
  response_schema
  immutable_context_refs
```

### Workspace change input

```text
GenericWorkspaceInput
  objective
  repository_binding
  base_ref
  base_sha
  allowed_paths
  acceptance_commands
  immutable_context_refs
```

### Media input

Reserved for later visual/audio workloads.

Rack AI is allowed to understand repository/workspace safety because that is generic execution infrastructure. It is not allowed to interpret the objective as a scenario, frontier, repair, or review.

## Generic execution constraints

Possible generic constraints include:

- timeout;
- network policy;
- filesystem/path policy;
- process policy;
- required artifacts;
- output size bounds;
- cancellation behavior.

These remain generic and enforceable by the backend.

## Generic acknowledgement and status

```text
SubmissionAcknowledgement
  submission_id
  backend_job_id
  accepted
  queued_at
  contract_version
```

```text
GenericJobStatus
  submission_id
  state: queued | selected | running | terminal | cancelled | blocked
  selected_worker_summary, optional
  updated_at
  evidence_refs
```

Temporary absence of capacity is `queued`, not capability failure.

No registered worker satisfying the hard generic requirements is `capability_unavailable`.

## Generic terminal result

```text
GenericAiJobResult
  work_id
  submission_id
  terminal_status
  output
  artifact_refs
  candidate_revision, optional
  selection_decision
  execution_provenance
  duration
  generic_failure
  evidence_refs
```

The connector translates transport fields but does not decide whether the result is valid RED, candidate defect, semantic repair, or regression failure. ATHBA interprets that after receipt.

## Selection evidence versus execution provenance

Rack AI returns two linked generic records.

### Selection decision

Explains why a worker was chosen:

```text
GenericSelectionDecision
  decision_id
  submission_id
  requested_capabilities
  requested_complexity
  requested_large_context
  requested_priority
  eligible_worker_ids
  ineligible_workers_with_generic_reasons
  selected_worker_id
  selection_reason
  policy_version
  resource_evidence
```

Allowed generic reasons may include:

- least_scarce_sufficient;
- only_eligible;
- higher_throughput;
- warm_model;
- capability_required;
- queue_priority;
- operator_policy.

They must not include `scenario_authoring`, `frontier`, or another ATHBA term.

### Execution provenance

Proves what actually ran:

```text
WorkerExecutionProvenance
  worker_id
  model_profile_id
  provider_profile
  resource_id
  backend
  harness_profile
```

Selection and execution worker IDs must agree. A mismatch fails closed.

## Rack AI worker/model registration

The generic target registry separates model capability from runtime placement.

### Model profile

```text
GenericModelProfile
  model_profile_id
  capabilities
  max_complexity_by_capability
  large_context_eligible
  context_window
  qualification_status
  qualification_evidence_refs
  profile_version
```

### Worker runtime

```text
GenericWorkerRuntime
  worker_id
  model_profile_id
  harness
  execution_forms
  resource_requirements
  status
  concurrency_capacity
  active_leases
```

### Physical resource

```text
GenericResource
  resource_id
  resource_kind
  memory_capacity
  health
  lease_state
  supported_runtime_profiles
```

The same model profile may have several worker runtimes on different GPUs. They expose the same model intelligence/capability profile while differing in throughput, warm state, and availability.

## Current mapping examples

### Coding-only small job

Request:

```text
capabilities: [coding]
complexity: small
requires_large_context: false
priority: medium or high
```

Current eligible profiles:

- local-coder profile;
- local-primary profile, if registered as coding-capable.

Generic ranking should normally select the least-scarce sufficient coding worker, preserving reasoning capacity.

### Reasoning-plus-coding job

Request:

```text
capabilities: [reasoning, coding]
complexity: medium
requires_large_context: false
priority: high
```

The coding-only profile is ineligible. A current primary profile is eligible.

### Reasoning-only review

Request:

```text
capabilities: [reasoning]
complexity: medium
priority: high
execution_form: structured_response
```

Rack AI chooses any qualified reasoning worker without knowing this is a review.

## ATHBA internal mapping

The connector never receives `AthbaWorkKind` directly.

An ATHBA-owned resolver produces a generic profile:

```text
AthbaExecutionProfile
  capabilities
  complexity
  requires_large_context
  priority
  execution_form
  timeout_seconds
```

Example internal mapping:

```text
scenario_authoring
  -> [reasoning, coding], medium, high, workspace_change

frontier_implementation_tier_1
  -> [coding], small, high, workspace_change

frontier_implementation_tier_2
  -> [reasoning, coding], medium, high, workspace_change
```

Only the right side crosses the boundary.

## Polymorphic ATHBA port

Conceptual protocol:

```text
AiExecutionPort
  submit(request) -> SubmissionAcknowledgement
  get_status(submission_id) -> GenericJobStatus
  get_result(submission_id) -> GenericAiJobResult
  cancel(submission_id) -> CancellationResult
```

Implementations:

```text
RackAiConnector
DeterministicFakeConnector
AlternativeRackConnector
```

ATHBA domain code must not import Rack AI CLI packet types directly after migration. Backend-specific mapping remains in the connector package.

## Dependency and pool boundary

The target connector does not send an ATHBA dependency graph.

ATHBA:

- knows dependency edges;
- marks work ready;
- withholds blocked work;
- submits all currently dispatchable ready items;
- unlocks new work after terminal interpretation.

Rack AI:

- queues already-ready generic jobs;
- selects workers/resources;
- returns status and terminal evidence.

An existing compatibility field such as `depends_on` may remain readable during migration, but it must not become Rack AI's authority for ATHBA execution order.

## Priority ownership

ATHBA chooses priority from its internal critical-path policy and sends only the generic enum.

Rack AI may combine priority with queue age and operator-wide workload policy.

Rules:

- `paramount` is rare and must be explicitly justified;
- Rack AI may not rewrite required capabilities because of priority;
- priority may affect when a job runs, never whether its result is semantically accepted;
- the connector persists the priority actually submitted.

## Escalation through generic profiles

ATHBA owns escalation semantics.

For one stable `work_id`:

```text
Tier 1 submission
  capabilities: [coding]
  complexity: small

Tier 2 submission after ATHBA exhaustion decision
  capabilities: [reasoning, coding]
  complexity: medium
```

Rack AI sees two generic submissions with different requirements. It does not need an `escalation_tier` software-development field.

ATHBA persists:

- tier;
- attempts consumed;
- candidate history;
- reason the generic profile changed.

Rack AI persists:

- each generic request;
- each selection decision;
- each execution result.

## Failure mapping

### Generic backend failures

Examples:

- no eligible capability;
- worker unavailable;
- resource unavailable;
- executor failure;
- transport failure;
- timeout;
- malformed packet;
- selection/provenance mismatch.

The connector maps these to typed backend-neutral failures.

ATHBA then decides whether the failure:

- consumes a model attempt;
- blocks externally;
- permits repair;
- authorizes a stronger generic profile.

The connector must not make that software-development decision.

## Replaceability test

The architecture is portable only if a test can replace Rack AI with a fake or alternative connector and run the same ATHBA transition sequence without changing:

- Behavior Contract logic;
- scenario state;
- frontier decomposition;
- RED/GREEN classification;
- attempt accounting;
- revision trust rules;
- Gatekeeper reconciliation.

Backend replacement may change worker identities and scheduling, but not ATHBA semantics.

## Minimum Rack AI change implied by this contract

The target Rack AI extension is deliberately smaller than the first PR27 draft:

1. replace or extend singular `implementation` capability with the generic capability set `reasoning`, `coding`, `visual`, `audio`;
2. retain `small`, `medium`, `large` complexity;
3. retain `requires_large_context`;
4. add `low`, `medium`, `high`, `paramount` priority;
5. register generic model capabilities and qualification envelopes;
6. select workers using only generic fields and resource state;
7. return generic selection evidence linked to execution provenance;
8. accept opaque IDs and generic execution forms;
9. do not add ATHBA work kinds or dependency semantics.

Detailed multi-GPU optimization, ComfyUI arbitration, and model-residency policy remain a separate Rack AI specification.

## Compatibility and migration

Version 1 migration should be additive:

- old `capability=implementation` requests remain readable during a bounded compatibility period;
- the connector emits the new version only after Rack AI supports it;
- old packets remain readable;
- selection evidence is optional for historical packets and mandatory for new capability-routed proofs;
- no live routing changes until deterministic connector and selector tests pass.

## Acceptance criteria

The connector contract is accepted when:

- no software-engineering stage crosses the boundary;
- capability values are only broad model classes;
- priority has exactly four defined values;
- complexity and large-context semantics remain generic;
- ATHBA dependencies remain internal;
- the connector is polymorphic and replaceable;
- Rack AI selection is based only on generic requirements and resource state;
- one sequential qualification proves reasoning-plus-coding, coding-only, and stronger fallback requests choose appropriate current workers;
- selection evidence matches execution provenance.
