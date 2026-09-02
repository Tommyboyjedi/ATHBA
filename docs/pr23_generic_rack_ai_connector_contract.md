# PR23 Generic Rack AI Workspace Connector Contract

## Status

Documentation-only connector proposal.

This document defines the anti-corruption layer between ATHBA's software-development domain and Rack AI's generic bounded workspace executor.

It supersedes the earlier PR27 proposal to place `execution_form` on one universal job request.

## Decision

For PR23, ATHBA needs one backend operation:

```text
bounded workspace change
```

The operation is selected by the connector method or Rack AI endpoint, not by an `execution_form` field.

This reflects current Rack AI reality: `rack-ai/work-unit/v1` already translates one ready application-development work unit into the existing bounded change path. Rack AI does not currently implement generic `structured_response` or `media_artifact` job forms.

Reasoning-only ATHBA work remains behind ATHBA's existing `ReasoningGateway` in this phase. Future generic inference, visual, audio, ComfyUI, and media-pipeline operations require a separate Rack AI specification.

## Layering

```text
ATHBA domain
  internal stages, dependencies, TDD state, attempts, revisions

ATHBA ExecutionProfileResolver
  maps an internal stage to broad model capabilities and generic routing values

AiWorkspaceExecutionPort
  backend-neutral bounded-workspace submission/status/result contract

RackAiWorkspaceConnector
  serializes the generic workspace request and translates generic results

Rack AI workspace executor
  queue, worker/model/resource selection, trusted worktree execution, evidence
```

Rules:

- the resolver knows ATHBA stages but not Rack AI transport;
- the connector knows the workspace transport but not ATHBA stage meaning;
- Rack AI receives no ATHBA work kind;
- a future backend can replace Rack AI by implementing the same port.

## Generic capability vocabulary

Version 1 defines four broad model classes:

```text
reasoning
coding
visual
audio
```

The field is a non-empty set:

```text
[coding]
[reasoning]
[reasoning, coding]
[visual]
[audio]
```

Rules:

- capabilities describe broad model types;
- no scenario, Tester, Developer, frontier, repair, review, or Gatekeeper term is a capability;
- no model, worker, endpoint, or GPU ID is a capability;
- unknown required capabilities fail closed;
- capability expansion requires a versioned contract;
- detailed development meaning stays inside ATHBA;
- measured model qualification stays inside Rack AI configuration/evidence.

## Generic complexity

```text
small
medium
large
```

Complexity is a generic size/difficulty envelope used against a registered model's qualified envelope.

It is not priority and does not imply semantic readiness.

## Context requirement

```text
requires_large_context: bool
```

Rack AI determines which registered profiles satisfy it.

## Global priority vocabulary

Rack AI may define:

```text
low
medium
high
paramount
```

Priority controls rack-wide queue/resource arbitration only. It does not alter required capabilities or semantic acceptance.

## ATHBA priority contract

ATHBA is a slow-burn background source and may submit only:

```text
low
medium
```

Meaning within the connector:

```text
low
  background ATHBA work that may wait behind normal rack demand

medium
  ordinary ready ATHBA work, including work blocking progress inside ATHBA
```

ATHBA must never submit:

```text
high
paramount
```

Those values are reserved for other explicitly authorized rack workloads or operator/system policy, including future interactive media demand, urgent service restoration, or resource-drain decisions.

Enforcement is defense in depth:

1. the ATHBA resolver type exposes only `low` and `medium`;
2. `RackAiWorkspaceConnector` rejects any ATHBA request above `medium`;
3. Rack AI source/admission policy records an ATHBA maximum of `medium` and rejects forged higher priority.

Rack AI may schedule or drain ATHBA work because a higher-priority external workload arrived. It must not promote ATHBA's own priority.

## Conceptual port

```text
AiWorkspaceExecutionPort
  submit_workspace_change(request) -> SubmissionAcknowledgement
  get_status(submission_id) -> WorkspaceJobStatus
  get_result(submission_id) -> WorkspaceJobResult
  cancel(submission_id) -> CancellationResult
```

Implementations:

```text
RackAiWorkspaceConnector
DeterministicFakeWorkspaceConnector
AlternativeWorkspaceBackendConnector
```

ATHBA domain code depends on the port, not Rack AI CLI or packet classes.

## Request

```text
GenericWorkspaceJobRequest
  contract_version
  source_system
  work_id
  submission_id
  idempotency_key
  capabilities: set[GenericModelCapability]
  complexity: GenericComplexity
  requires_large_context: bool
  priority: AthbaOutboundPriority
  timeout_seconds
  objective
  repository_binding
  base_ref
  base_sha
  allowed_paths
  acceptance_commands
  required_artifacts
  environment_resources
  network_policy
  evidence_refs
```

No field carries ATHBA stage, TDD phase, dependency meaning, model tier, worker ID, model ID, GPU ID, or JCode profile.

### Identity

`work_id`:

- stable across attempts and ATHBA-internal stronger-route changes;
- opaque to Rack AI;
- never reused for different semantic work.

`submission_id`:

- unique for every actual backend submission;
- stable across connector delivery retry;
- correlates acknowledgement, status, and terminal result.

`idempotency_key`:

- prevents duplicate execution of one submission;
- is not a dependency or sequence mechanism.

An audit sequence may be sent, but Rack AI must not infer semantic ordering from it.

## Acknowledgement and status

```text
SubmissionAcknowledgement
  submission_id
  backend_job_id
  accepted
  queued_at
  contract_version
```

```text
WorkspaceJobStatus
  submission_id
  state: queued | selected | running | terminal | cancelled | blocked
  selected_worker_summary, optional
  updated_at
  evidence_refs
```

Temporary lack of capacity is `queued`.

No registered model satisfying hard capabilities is `capability_unavailable`.

Invalid ATHBA priority is `source_priority_rejected`.

## Terminal result

```text
WorkspaceJobResult
  work_id
  submission_id
  terminal_status
  candidate_revision, optional
  branch, optional
  worktree_ref, optional
  changed_paths
  acceptance_result
  selection_decision
  execution_provenance
  duration
  generic_failure
  evidence_refs
```

The connector translates transport and generic executor facts. It does not decide whether a result is valid RED, candidate defect, semantic repair, regression failure, or reason to escalate.

## Selection evidence

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

Allowed reasons are generic, for example:

```text
least_scarce_sufficient
only_eligible
higher_throughput
warm_model
capability_required
queue_priority
operator_policy
```

Selection reasons must not contain ATHBA stage terminology.

## Execution provenance

Existing Rack AI `WorkerExecutionProvenance` proves what actually ran:

```text
worker_id
model_profile_id
provider_profile
resource_id
backend
harness_profile
```

The selected and executed worker must agree. A mismatch fails closed.

## Current model profile examples

```text
Qwen local-coder profile
  capabilities: [coding]
  qualified complexity: small and selected bounded medium coding tasks
  large context: no
```

```text
Gemma primary profile
  capabilities: [reasoning, coding]
  qualified complexity: medium/large within measured limits
  large context: yes
```

A future 4080 runtime using the same Gemma profile exposes the same capabilities while differing in throughput and availability.

## Eligibility and ranking

Hard filters:

1. all requested capabilities supported;
2. qualification covers complexity;
3. context requirement satisfied;
4. runtime/resource healthy or queueable;
5. workspace constraints enforceable;
6. source priority accepted.

Ranking may use:

- least-scarce sufficient profile;
- availability and leases;
- warm model state;
- measured throughput;
- expected duration;
- queue age;
- global priority;
- deterministic tie-break.

For `[coding]`, small, the coding-only worker is normally preferred. For `[reasoning, coding]`, it is ineligible.

## ATHBA internal mapping examples

Only the right-hand side crosses the connector.

```text
scenario authoring
  -> [reasoning, coding], medium complexity, medium priority

frontier implementation tier 1
  -> [coding], small complexity, low or medium priority

frontier implementation stronger route
  -> [reasoning, coding], medium complexity, medium priority
```

There is no `execution_form` because all three use the workspace port.

## Dependency and queue boundary

ATHBA:

- owns dependencies and semantic readiness;
- withholds blocked work;
- submits each currently dispatchable ready item once;
- unlocks new work after interpreting terminal results.

Rack AI:

- queues already-ready workspace jobs;
- selects workers/resources;
- enforces source priority;
- returns status and terminal evidence.

Rack AI does not sequence ATHBA dependencies.

## Stronger-route mapping

ATHBA owns why requirements change.

For one stable `work_id`:

```text
initial narrow submission
  capabilities: [coding]
  complexity: small
  priority: low or medium

stronger submission after ATHBA-internal exhaustion
  capabilities: [reasoning, coding]
  complexity: medium
  priority: medium
```

Rack AI sees generic submissions. It does not need an ATHBA escalation field.

## Current Rack AI change surface

The required change is bounded:

1. preserve existing `rack-ai/work-unit/v1` compatibility;
2. add a versioned or additive capability set;
3. retain small/medium/large complexity;
4. retain `requires_large_context`;
5. add global low/medium/high/paramount priority;
6. enforce source-specific priority ceilings, with ATHBA capped at medium;
7. add generic model capability and qualification metadata;
8. implement deterministic generic eligibility/ranking;
9. return selection evidence linked to execution provenance;
10. keep the existing trusted workspace-change executor unchanged.

Not required:

- a universal execution-form enum;
- structured-response execution through Rack AI;
- visual/audio/media executors;
- ATHBA work kinds;
- ATHBA dependency graphs;
- shared semantic pools;
- ComfyUI arbitration;
- three-GPU optimization;
- preemption;
- idle-primary overflow.

## Compatibility

Migration is additive:

- old `capability=implementation` requests remain readable during a bounded compatibility period and map to the legacy coding route;
- the connector emits the new contract only after Rack AI supports it;
- old packets remain readable;
- selection evidence is optional for historical packets and mandatory for new routed proofs;
- no live route changes until deterministic connector and selector tests pass.

## Acceptance criteria

The connector contract is accepted when:

- no software-engineering stage crosses the boundary;
- capabilities are only broad model classes;
- PR23 uses only the workspace operation;
- no `execution_form` field is required;
- ATHBA can emit only low/medium priority;
- Rack AI independently enforces the ATHBA priority ceiling;
- ATHBA dependencies remain internal;
- the port is polymorphic and replaceable;
- Rack AI selects only from generic requirements and resource state;
- selection evidence matches execution provenance;
- a sequential qualification proves reasoning-plus-coding, coding-only, and stronger generic requests select appropriate current workers.