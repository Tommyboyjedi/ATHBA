# Why ATHBA Uses a Generic Rack Execution Boundary

## Decision

ATHBA owns every software-development concept. Rack AI receives only an already-ready, bounded, generic AI workspace job through a replaceable connector.

The boundary exists so that neither repository quietly becomes the other one:

- ATHBA remains the software-development system;
- Rack AI remains the rack execution and resource-control system;
- prompts do not become an undocumented security, scheduling, or integration API;
- another execution backend can replace Rack AI without rewriting ATHBA's TDD domain.

## Why the boundary is necessary

ATHBA understands requirements, Behavior Contracts, scenarios, strict TDD frontiers, RED/GREEN meaning, candidate repair, attempt accounting, trusted revisions, semantic review, and final Gatekeeper reconciliation. Those concepts are meaningful only inside ATHBA.

Rack AI understands registered models, worker runtimes, GPU and other resource availability, leases, trusted worktrees, process execution, timeouts, network and path policy, deterministic command evidence, candidate revisions, and terminal packets. Those are generic execution concerns that should not be reimplemented by every client of the rack.

Teaching Rack AI about Tester, Developer, scenario repair, or a TDD frontier would couple it to ATHBA. Reducing Rack AI to a raw prompt forwarder would instead force ATHBA to duplicate privileged execution, worktree, resource, timeout, and evidence machinery. The correct boundary keeps the software meaning in ATHBA and the secured physical execution in Rack AI.

## The connector is an anti-corruption layer

ATHBA depends on a backend-neutral port. A Rack AI connector implements that port, but Rack AI transport types must not leak into ATHBA's development domain.

Conceptually:

```text
ATHBA internal development state
  -> ATHBA execution-profile resolver
  -> generic workspace request
  -> AiWorkspaceExecutionPort
  -> RackAiWorkspaceConnector
  -> Rack AI
```

The execution-profile resolver knows ATHBA stages but not Rack AI transport. The connector knows Rack AI transport but not ATHBA stage semantics.

A future alternative backend can implement the same port without changing:

- Behavior Contract logic;
- scenario and frontier state;
- RED/GREEN interpretation;
- model-attempt accounting;
- trusted-revision rules;
- Gatekeeper reconciliation.

## What ATHBA keeps internal

The following never cross the connector boundary as routing terms:

- behavior planning;
- Tester or Developer role;
- complete scenario authoring or repair;
- strict TDD frontier;
- RED or GREEN;
- regression repair;
- senior review;
- Gatekeeper stage;
- ATHBA dependency graph;
- ATHBA escalation tier;
- reason a result consumes an ATHBA model attempt.

ATHBA may use all of these concepts internally when deciding that work is ready and when interpreting the result.

## What ATHBA may send

For the current bounded workspace operation, ATHBA sends three deliberately separate parts.

### 1. Generic routing header

```text
capabilities: one or more of
  reasoning
  coding
  visual
  audio

complexity:
  small
  medium
  large

requires_large_context:
  true | false

priority from ATHBA:
  low | medium
```

These are broad model and scheduling requirements, not software-engineering terms.

ATHBA may never submit `high` or `paramount`. ATHBA is continuous slow-burn work. Even work that blocks an ATHBA project is at most medium priority to the rack as a whole. High and paramount remain available to Rack AI for other authorized interactive, operational, safety, restoration, or media workloads.

The ATHBA connector must reject an outbound priority above medium. Rack AI should independently enforce a source-system admission ceiling so a buggy or forged ATHBA request cannot exceed medium.

### 2. Machine-enforced execution envelope

```text
source system and opaque identities
repository identity
exact base ref and SHA
allowed writable paths
authorized read-only resources
timeout and network policy
required artifacts
deterministic acceptance commands
idempotency and cancellation data
```

This envelope is authoritative. It is enforced whether or not the model follows the prompt.

### 3. Minimal model-facing task payload

```text
bounded objective
relevant immutable context
expected artifact
prior failure evidence when applicable
```

The prompt explains the job, but it is not the trust boundary.

> The prompt is advisory. The typed execution envelope is authoritative.

Permissions, paths, timeout, routing, identity, and acceptance must not exist only as prose in the prompt.

## Capability request versus Rack AI metadata

ATHBA sends only the capability requirement for the current job, for example:

```text
[coding]
[reasoning]
[reasoning, coding]
```

ATHBA does not send a model capability catalogue or qualification record.

Rack AI owns internal model eligibility profiles describing which registered models can satisfy which broad capabilities, complexity and context envelopes. Those profiles may contain qualification evidence, constraints, context size, runtime status, throughput, and resource placement. They are Rack AI configuration and evidence, not ATHBA input.

The request says:

```text
I need reasoning and coding.
```

Rack AI's internal catalogue answers:

```text
Which healthy, available or queueable worker runtimes are qualified to provide that?
```

Rack AI may return selection evidence and execution provenance. ATHBA uses that evidence for audit and fail-closed verification; it does not author Rack AI's model metadata.

## Why Rack AI owns the bounded workspace transaction

A bounded workspace transaction is one generic operation:

```text
validate exact repository/base
create isolated worktree
select eligible worker and resource
invoke the registered harness
restrict writes to declared paths
enforce network/process/time limits
inspect the actual Git diff
run caller-supplied deterministic acceptance
return candidate revision and evidence, or a terminal failure
```

This operation is useful beyond ATHBA and contains privileged, reusable infrastructure. Rack AI should own it so every client does not reinvent worker selection, GPU placement, worktree trust, sandboxing, timeout cleanup, Git evidence, and terminalization.

Rack AI does not decide whether the returned code is a valid scenario, valid RED, correct GREEN, semantic repair, or completed behavior. ATHBA makes those decisions after receiving the generic result.

## Dispatch and queue ownership

There is no shared semantic pool.

ATHBA owns one authoritative work ledger containing dependencies, readiness, TDD state, attempt state, trusted revisions, and project-mutation rules. ATHBA submits only work that it has already determined is ready and dispatchable.

Rack AI queues only already-ready generic jobs. It owns queue order, source priority, worker/resource eligibility, leases, execution, and terminal evidence.

Rack AI does not sequence ATHBA dependencies. If work B depends on work A, ATHBA simply withholds B until A has completed and ATHBA has interpreted the result.

A stable `work_id` identifies the same logical ATHBA work across attempts and stronger-profile escalation. A unique `submission_id` identifies one actual backend model invocation. Rack AI treats both as opaque identifiers.

## One submission means one model invocation

ATHBA owns semantic attempt policy. One submitted `submission_id` normally corresponds to one actual model invocation.

Rack AI may retry low-level infrastructure operations that do not create a second semantic model attempt, but it must not silently perform several model submissions behind one ATHBA submission ID. Execution provenance must make the actual invocation count auditable.

This separation allows ATHBA to enforce four genuine model submissions without confusing infrastructure recovery with another Tester or Developer attempt.

## Failure ownership

Rack AI returns generic execution facts such as:

- no eligible capability;
- worker unavailable;
- resource unavailable;
- timeout;
- transport or executor failure;
- malformed or incomplete packet;
- selection/provenance mismatch;
- candidate revision and changed paths;
- command results.

ATHBA interprets those facts using its own domain and decides whether they consume a model attempt, authorize repair, block externally, or justify a stronger generic capability request.

Neither side may cross the repository boundary to repair the other side's responsibility.

## Dynamic hardware remains invisible to ATHBA

A model profile and a physical GPU are separate Rack AI concepts. Two worker runtimes may run the same model profile on a 4060 Ti and a 4080 Super. They expose the same broad intelligence capabilities but differ in speed, warm state, and availability.

If another workload leases the 4080, Rack AI may queue ATHBA work or use another eligible worker. ATHBA's generic request does not change and ATHBA does not need to know which GPU was removed.

Detailed ComfyUI arbitration, three-GPU placement, model residency, preemption, and idle-worker optimization belong to a separate Rack AI scheduling specification. They must preserve this boundary.

## Change-control rule

Any further harness change must demonstrate that it restores an existing generic contract rather than merely allowing a live proof to move one step forward.

Model output that violates a documented contract is not, by itself, evidence that the harness must change.

Consequences:

- do not add a tool merely because a model attempted to call it;
- do not loosen the test grammar merely because a model generated an unsupported form;
- do not expose a new ATHBA stage to Rack AI because one routing case is inconvenient;
- do not move attempt or dependency semantics into the connector;
- do not encode security, permissions, or acceptance only in prompt prose.

## Immediate implementation scope

For the PR23 route, the only Rack AI operation required is the existing bounded workspace transaction. The immediate cross-repository extension is limited to:

- broad capability sets;
- existing small/medium/large complexity;
- existing large-context flag;
- global priority with ATHBA capped at medium;
- internal Rack AI model eligibility profiles;
- generic worker selection evidence linked to execution provenance;
- backward-compatible opaque work/submission identity.

A universal inference/media job framework is not required to complete PR23.
