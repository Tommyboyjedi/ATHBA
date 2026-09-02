# PR23 Worker-Routing State Machines

## Status

Documentation-only companion to `pr23_worker_capability_routing_architecture.md`.

## Complete scenario authoring

```mermaid
stateDiagram-v2
    [*] --> ScenarioReady
    ScenarioReady --> SelectionRequested: ATHBA emits high-reasoning capability request
    SelectionRequested --> PrimarySelected: Rack AI selects qualified worker
    SelectionRequested --> CapabilityBlocked: no eligible worker
    PrimarySelected --> CandidateReturned: candidate source/ref/SHA returned
    PrimarySelected --> NoCandidate: model-originated terminal result
    PrimarySelected --> ExternalBlocked: executor/transport/selection failure
    CandidateReturned --> StructuralRejected: language adapter rejects
    CandidateReturned --> IntentPending: structural acceptance
    StructuralRejected --> RepairRequested: submissions remain
    IntentPending --> IntentApproved: independent review approves
    IntentPending --> RepairRequested: semantic repair required
    IntentPending --> ReviewerBlocked: review protocol/infrastructure failure
    RepairRequested --> PrimarySelected: next bounded primary submission
    NoCandidate --> PrimarySelected: fresh retry and submissions remain
    NoCandidate --> CapabilityBlocked: fourth submission exhausted
    IntentApproved --> ScenarioFrozen
    ScenarioFrozen --> [*]
    ExternalBlocked --> [*]
    ReviewerBlocked --> [*]
    CapabilityBlocked --> [*]
```

Scenario authoring uses one high-reasoning tier with at most four actual model submissions. Infrastructure failures do not consume the model budget.

## Deterministic frontier progression

```mermaid
flowchart TD
    A[Approved frozen scenario] --> B[Language adapter parses scenario]
    B --> C[Ordered syntactically complete fragments]
    C --> D[Materialise smallest active frontier]
    D --> E[Deterministic parse / collect / execute]
    E -->|valid missing capability or wrong behavior| F[Accepted RED frontier]
    E -->|artifact invalid| G[Adapter or scenario failure]
    E -->|infrastructure invalid| H[External blocker]
    F --> I[Submit narrow implementation work]
    I --> J[Focused GREEN verification]
    J -->|pass| K[Accumulated deterministic regression]
    J -->|fail| L[Bounded implementation repair or escalation]
    K -->|pass| M[CAS canonical promotion]
    K -->|fail| N[Bounded regression repair or escalation]
    M --> O{More fragments?}
    O -->|yes| D
    O -->|no| P[Complete canonical scenario GREEN]
    P --> Q[Behavior-level review]
```

No model creates intermediate fragment tests. The same canonical test evolves through history.

## Narrow implementation and escalation

```mermaid
stateDiagram-v2
    [*] --> NarrowReady
    NarrowReady --> CoderSelection: required capability bounded_code_edit
    CoderSelection --> CoderAttempt
    CoderAttempt --> Accepted: deterministic gates clear
    CoderAttempt --> CoderRetry: genuine model failure and attempts remain
    CoderRetry --> CoderAttempt
    CoderAttempt --> PrimaryEscalation: fourth coder submission fails
    CoderAttempt --> ExternalBlocked: infrastructure failure
    PrimaryEscalation --> PrimaryAttempt
    PrimaryAttempt --> Accepted: deterministic gates clear
    PrimaryAttempt --> PrimaryRetry: genuine model failure and attempts remain
    PrimaryRetry --> PrimaryAttempt
    PrimaryAttempt --> CapabilityBlocked: fourth primary submission fails
    PrimaryAttempt --> ExternalBlocked: infrastructure failure
    Accepted --> [*]
    CapabilityBlocked --> [*]
    ExternalBlocked --> [*]
```

There is no transition from the primary fallback tier back to the coder tier.

## Per-tier attempt accounting

```mermaid
flowchart LR
    W[Immutable work identity] --> T1[Tier 1 local-coder preferred]
    T1 --> A1[submission 1]
    A1 --> A2[submission 2]
    A2 --> A3[submission 3]
    A3 --> A4[submission 4]
    A4 --> X{success?}
    X -->|yes| Done[continue normal TDD]
    X -->|no| T2[Tier 2 local-primary fallback]
    T2 --> B1[submission 1]
    B1 --> B2[submission 2]
    B2 --> B3[submission 3]
    B3 --> B4[submission 4]
    B4 --> Y{success?}
    Y -->|yes| Done
    Y -->|no| Block[capability_blocked]
```

Every actual invocation has a unique submission and change identity. Process restart cannot reset either tier.

## ATHBA ready pool to Rack AI execution queue

```mermaid
sequenceDiagram
    participant A as ATHBA semantic ready pool
    participant R as Rack AI execution queue
    participant S as Rack AI selector
    participant W as Selected worker
    A->>R: immutable DevelopmentWorkDescriptor
    R-->>A: durable submission acknowledgement
    R->>S: request eligibility and resource selection
    S-->>R: WorkerSelectionDecision
    R->>W: bounded work invocation
    W-->>R: terminal execution evidence
    R-->>A: terminal packet + selection + provenance
    A->>A: interpret candidate and advance TDD state
```

ATHBA alone decides semantic readiness. Rack AI alone decides concrete worker/resource availability.

## Worker selection and execution provenance

```mermaid
flowchart TD
    A[Work kind and required capabilities] --> B[Capability registry lookup]
    B --> C[Eligible workers]
    B --> D[Ineligible workers with reasons]
    C --> E[Resource and lease filtering]
    E --> F[Priority policy]
    F --> G[WorkerSelectionDecision]
    G --> H[Worker invocation]
    H --> I[WorkerExecutionProvenance]
    I --> J{Selected worker equals executed worker?}
    J -->|yes| K[Return terminal packet]
    J -->|no| L[Fail closed: provenance mismatch]
```

Selection evidence explains **why** a worker was selected. Execution provenance proves **what** ran.

## Idle-primary overflow

```mermaid
stateDiagram-v2
    [*] --> PrimaryIdle
    PrimaryIdle --> HighReasoningLease: high-reasoning work ready
    PrimaryIdle --> EscalatedLease: no high-reasoning work; escalated narrow work ready
    PrimaryIdle --> OverflowLease: no high-reasoning or escalated work; overflow eligible
    OverflowLease --> OverflowRunning
    OverflowRunning --> PrimaryIdle: bounded task finishes
    HighReasoningLease --> HighReasoningRunning
    HighReasoningRunning --> PrimaryIdle: task finishes
    EscalatedLease --> EscalatedRunning
    EscalatedRunning --> PrimaryIdle: task finishes
```

Version 1 is non-preemptive. If high-reasoning work arrives during a bounded overflow task, the running task finishes, but no additional overflow lease is issued.

## Project mutation lock

```mermaid
flowchart TD
    A[Ready mutating work] --> B{Project mutation lane free?}
    B -->|no| C[Remain semantically ready but unleased]
    B -->|yes| D[Acquire project mutation lease]
    D --> E[Execute against exact base ref/SHA]
    E --> F{Terminal candidate accepted?}
    F -->|no| G[Release lease; preserve trusted base]
    F -->|yes| H[Compare-and-swap canonical promotion]
    H -->|CAS pass| I[Persist new canonical revision]
    H -->|CAS fail| J[Reject stale result]
    I --> K[Release lease]
    J --> K
    G --> K
```

One active mutating lane per project is the version-1 rule. Independent projects may execute concurrently.

## Failure ownership matrix

| Event | Consumes model submission? | Primary owner | Next action |
| --- | --- | --- | --- |
| Structurally invalid candidate | Yes | ATHBA | repair within current tier |
| Semantic repair disposition | Yes | ATHBA | repair within current tier |
| Model uses unadvertised tool / no candidate | Yes | ATHBA using Rack AI evidence | fresh retry within current tier |
| Worker timeout after verified invocation | Yes | Rack AI evidence + ATHBA tier policy | next bounded submission or escalation |
| Worker not selected | No | Rack AI | external/capability blocker |
| Executor/transport/worktree failure | No | Rack AI | external blocker |
| No eligible worker | No | Rack AI selection | capability blocker |
| Malformed terminal packet/provenance mismatch | No | cross-boundary contract | fail closed |
| Focused GREEN failure | Yes | ATHBA | repair current tier |
| Deterministic regression failure | Yes when repair model invoked | ATHBA | bounded repair / escalation |
| Four coder submissions fail | N/A | ATHBA | authorize primary tier |
| Four primary submissions fail | N/A | ATHBA | capability-blocked terminal state |

## Resume invariants

Persisted state must retain:

- immutable work ID;
- current tier;
- submissions consumed within each tier;
- global submission sequence;
- last selected worker decision;
- actual execution provenance;
- candidate and no-candidate history;
- repair and escalation parents;
- base ref/SHA and allowed paths;
- pending transition receipt;
- canonical revision and project mutation lease state.

A completed frontier, model submission, selection decision, or promotion must not be repeated after restart.
