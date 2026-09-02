# PR23 Generic Workspace Routing State Machines

## Status

Documentation-only companion to the routing architecture.

ATHBA stage names remain inside ATHBA. Rack AI sees only generic workspace jobs with capability, complexity, context, low/medium ATHBA priority, opaque identity, and bounded execution constraints.

## Complete scenario authoring

```mermaid
stateDiagram-v2
    [*] --> ScenarioReady
    ScenarioReady --> ProfileResolved: ATHBA maps stage internally
    ProfileResolved --> WorkspaceSubmitted: reasoning+coding / medium / priority medium
    WorkspaceSubmitted --> WorkerSelected: Rack AI generic selection
    WorkspaceSubmitted --> BackendBlocked: admission, capability, or executor blocker
    WorkerSelected --> CandidateReturned: source/ref/SHA
    WorkerSelected --> NoCandidate: model-originated terminal result
    CandidateReturned --> StructuralRejected: deterministic adapter rejects
    CandidateReturned --> IntentPending: structural acceptance
    StructuralRejected --> RepairReady: submissions remain
    NoCandidate --> FreshRetryReady: submissions remain
    RepairReady --> WorkspaceSubmitted: same generic profile
    FreshRetryReady --> WorkspaceSubmitted: same generic profile
    IntentPending --> IntentApproved: independent ATHBA review
    IntentPending --> SemanticRepairReady: explicit semantic repair result
    IntentPending --> ReviewerBlocked: protocol/infrastructure failure
    SemanticRepairReady --> WorkspaceSubmitted: same generic profile
    IntentApproved --> ScenarioFrozen
    ScenarioFrozen --> [*]
    BackendBlocked --> [*]
    ReviewerBlocked --> [*]
```

Rack AI never receives `ScenarioReady`, `RepairReady`, or intent terminology.

## Deterministic frontier progression

```mermaid
flowchart TD
    A[Approved frozen scenario] --> B[ATHBA language adapter parses]
    B --> C[Ordered syntactically complete fragments]
    C --> D[Materialise smallest active frontier]
    D --> E[Deterministic parse / collect / execute]
    E -->|valid active-boundary failure| F[Accepted RED frontier]
    E -->|artifact invalid| G[ATHBA adapter/scenario route]
    E -->|infrastructure invalid| H[External blocker]
    F --> I[ATHBA maps implementation to coding/small]
    I --> J[Submit bounded workspace job]
    J --> K[Focused deterministic GREEN]
    K -->|pass| L[Accumulated deterministic regression]
    K -->|fail| M[ATHBA repair/tier policy]
    L -->|pass| N[CAS canonical promotion]
    L -->|fail| O[ATHBA regression-repair policy]
    N --> P{More fragments?}
    P -->|yes| D
    P -->|no| Q[Complete canonical scenario GREEN]
    Q --> R[Behavior-level review]
```

No model creates intermediate tests.

## Coding-first implementation and stronger route

```mermaid
stateDiagram-v2
    [*] --> NarrowReady
    NarrowReady --> CoderProfile: ATHBA maps to coding/small/low-or-medium
    CoderProfile --> Submitted
    Submitted --> CoderSelected: Rack AI least-scarce sufficient selection
    Submitted --> ExternalBlocked: no eligible/available execution path
    CoderSelected --> Accepted: deterministic gates clear
    CoderSelected --> ModelFailure: candidate or no-candidate failure
    ModelFailure --> CoderProfile: attempts remain
    ModelFailure --> StrongerProfile: fourth coder-tier failure
    StrongerProfile --> StrongerSubmitted: reasoning+coding/medium/priority medium
    StrongerSubmitted --> StrongerSelected
    StrongerSelected --> Accepted: deterministic gates clear
    StrongerSelected --> StrongerFailure
    StrongerFailure --> StrongerProfile: attempts remain
    StrongerFailure --> CapabilityBlocked: fourth stronger-tier failure
    Accepted --> [*]
    ExternalBlocked --> [*]
    CapabilityBlocked --> [*]
```

Rack AI sees only the generic profile change. ATHBA owns why it changed.

## ATHBA ledger to Rack AI queue

```mermaid
sequenceDiagram
    participant A as ATHBA semantic ledger
    participant C as RackAiWorkspaceConnector
    participant R as Rack AI generic queue
    participant S as Rack AI selector
    participant W as Selected worker
    A->>A: resolve dependencies/readiness
    A->>A: choose dispatchable ready work
    A->>C: internal work + generic profile
    C->>C: enforce ATHBA priority <= medium
    C->>R: opaque bounded workspace request
    R->>R: source admission; reject ATHBA high/paramount
    R-->>C: durable acknowledgement
    R->>S: capability/context/complexity/resource selection
    S-->>R: generic selection decision
    R->>W: bounded workspace execution
    W-->>R: terminal execution evidence
    R-->>C: result + selection + provenance
    C-->>A: backend-neutral result
    A->>A: interpret using development semantics
```

There is no shared dependency pool.

## Priority boundary

```mermaid
flowchart TD
    A[ATHBA ready work] --> B{ATHBA internal urgency}
    B -->|background| C[Outbound low]
    B -->|normal or blocking within ATHBA| D[Outbound medium]
    B -->|attempt high/paramount| E[Connector rejects]
    C --> F[Rack AI source admission]
    D --> F
    F -->|source=ATHBA and priority<=medium| G[Queue]
    F -->|source=ATHBA and priority>medium| H[Reject source priority]
    I[Other authorized source high/paramount] --> J[Rack AI global arbitration]
    G --> J
```

High/paramount remain available to Rack AI for other authorized workloads and future resource-drain policy.

## Selection and execution provenance

```mermaid
flowchart TD
    A[Capabilities + complexity + context + priority] --> B[Source admission]
    B --> C[Model capability/qualification filter]
    C --> D[Runtime/resource availability]
    D --> E[Least-scarce sufficient ranking]
    E --> F[SelectionDecision]
    F --> G[Worker execution]
    G --> H[WorkerExecutionProvenance]
    H --> I{Selected worker equals executed worker?}
    I -->|yes| J[Return terminal packet]
    I -->|no| K[Fail closed]
```

## Per-tier attempt accounting

```mermaid
flowchart LR
    W[Stable ATHBA work_id] --> T1[Internal coding tier]
    T1 --> A1[submission 1]
    A1 --> A2[submission 2]
    A2 --> A3[submission 3]
    A3 --> A4[submission 4]
    A4 --> X{success?}
    X -->|yes| Done[normal TDD progression]
    X -->|no| T2[Internal stronger tier]
    T2 --> B1[submission 1]
    B1 --> B2[submission 2]
    B2 --> B3[submission 3]
    B3 --> B4[submission 4]
    B4 --> Y{success?}
    Y -->|yes| Done
    Y -->|no| Block[capability blocked]
```

Tier meaning does not cross the connector.

## Sequential proof gate

```mermaid
flowchart TD
    A[Selector unit tests] --> B[Sequential Rack AI request: reasoning+coding]
    B --> C[Sequential Rack AI request: coding/small]
    C --> D[Sequential stronger generic request]
    D --> E[Selection/provenance agreement]
    E --> F[Tiny ATHBA feature, one external job at a time]
    F --> G[Checkpoint/resume]
    G --> H[ReservationBook]
    H --> I[Later Rack AI concurrency specification]
```

No concurrency optimization is needed before `H`.

## Future resource withdrawal

```mermaid
stateDiagram-v2
    [*] --> DevelopmentCapacityAvailable
    DevelopmentCapacityAvailable --> HigherPriorityDemand: authorized high/paramount job arrives
    HigherPriorityDemand --> DrainAthbaCapacity: Rack AI global policy
    DrainAthbaCapacity --> ReducedDevelopmentCapacity
    ReducedDevelopmentCapacity --> CapacityRestored: external workload releases resource
    CapacityRestored --> DevelopmentCapacityAvailable
```

ATHBA continues to submit low/medium jobs and sees generic queued/running/terminal states. It never identifies the GPU being withdrawn.

## Resume invariants

Persisted ATHBA state retains:

- stable work identity;
- internal stage/tier;
- submissions consumed;
- candidate/no-candidate history;
- base ref/SHA and allowed paths;
- connector submission IDs;
- terminal results;
- canonical revision and transition receipts.

Rack AI persists:

- opaque request;
- source and accepted priority;
- selection decision;
- lease/execution state;
- execution provenance;
- terminal packet.

Completed submissions, frontiers, and promotions are never repeated after restart.