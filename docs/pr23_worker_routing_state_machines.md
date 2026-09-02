# PR23 ATHBA Routing and Generic Connector State Machines

## Status

Documentation-only companion to `pr23_worker_capability_routing_architecture.md`.

The diagrams distinguish:

- ATHBA's internal software-development state;
- ATHBA's generic execution-profile mapping;
- the replaceable connector boundary;
- Rack AI's generic queue and resource selection.

Rack AI does not receive ATHBA software-engineering work kinds.

## End-to-end boundary

```mermaid
flowchart LR
    A[ATHBA development state] --> B{Semantically ready?}
    B -->|no| C[Remain internal: blocked or pending]
    B -->|yes| D[ATHBA execution-profile resolver]
    D --> E[Generic AI job request]
    E --> F[AiExecutionPort]
    F --> G[RackAiConnector]
    G --> H[Rack AI generic queue]
    H --> I[Generic capability and resource selection]
    I --> J[Selected model worker resource]
    J --> K[Generic terminal result]
    K --> G
    G --> L[Generic result translated]
    L --> M[ATHBA interprets development meaning]
    M --> A
```

The software-development stage never crosses the connector boundary.

## ATHBA internal work ledger

```mermaid
stateDiagram-v2
    [*] --> Pending
    Pending --> Ready: dependencies and prior state satisfied
    Ready --> Dispatchable: project mutation and idempotency rules permit
    Dispatchable --> Submitted: connector acknowledgement persisted
    Submitted --> Queued: Rack AI acknowledges generic job
    Queued --> Running: Rack AI selects and leases capacity
    Running --> TerminalResult: generic terminal evidence returned
    TerminalResult --> Interpreting: ATHBA applies domain meaning
    Interpreting --> Completed: accepted development transition
    Interpreting --> Ready: bounded repair or next submission
    Interpreting --> Pending: new ATHBA dependency or later frontier
    Interpreting --> Blocked: external or capability blocker
    Completed --> [*]
    Blocked --> [*]
```

ATHBA may submit every item that is both semantically ready and dispatchable. It does not share its dependency graph or mutable semantic state with Rack AI.

## Rack AI generic queue

```mermaid
stateDiagram-v2
    [*] --> Received
    Received --> Validated: generic contract valid
    Received --> Rejected: invalid generic contract
    Validated --> Queued
    Queued --> WaitingForCapacity: eligible worker exists but is busy
    Queued --> CapabilityUnavailable: no worker satisfies hard requirements
    Queued --> Selected: eligible resource available
    WaitingForCapacity --> Selected: capacity becomes available
    Selected --> Running: lease acquired
    Running --> Terminal
    Terminal --> [*]
    Rejected --> [*]
    CapabilityUnavailable --> [*]
```

Rack AI understands only generic capability, complexity, context, priority, execution form, constraints, and opaque identity.

## Complete scenario authoring inside ATHBA

```mermaid
stateDiagram-v2
    [*] --> ScenarioReady
    ScenarioReady --> ProfileResolved: ATHBA maps internal stage
    ProfileResolved --> Submitted: capabilities reasoning plus coding
    Submitted --> CandidateReturned: workspace candidate exists
    Submitted --> NoCandidate: verified model-originated no-candidate result
    Submitted --> ExternalBlocked: executor or connector blocker
    CandidateReturned --> StructuralRejected: deterministic adapter rejects
    CandidateReturned --> IntentPending: structural acceptance
    StructuralRejected --> RepairProfile: submissions remain
    NoCandidate --> FreshRetryProfile: submissions remain
    IntentPending --> IntentApproved: independent review approves
    IntentPending --> RepairProfile: semantic repair required
    IntentPending --> ReviewerBlocked: review protocol or infrastructure failure
    RepairProfile --> Submitted: same generic reasoning plus coding profile
    FreshRetryProfile --> Submitted: same generic reasoning plus coding profile
    IntentApproved --> ScenarioFrozen
    ScenarioFrozen --> [*]
    ExternalBlocked --> [*]
    ReviewerBlocked --> [*]
```

Rack AI sees a generic `[reasoning, coding]` workspace job. It does not know it is authoring or repairing a scenario.

## Deterministic frontier progression

```mermaid
flowchart TD
    A[Approved frozen scenario] --> B[Language adapter parses]
    B --> C[Ordered syntactically complete fragments]
    C --> D[Materialise smallest active frontier]
    D --> E[Deterministic parse collect execute]
    E -->|valid missing capability or wrong behavior| F[Accepted RED frontier]
    E -->|artifact invalid| G[ATHBA adapter or scenario route]
    E -->|infrastructure invalid| H[External blocker]
    F --> I[Create internal narrow implementation work]
    I --> J[Map to generic coding small job]
    J --> K[Focused GREEN verification]
    K -->|pass| L[Accumulated deterministic regression]
    K -->|fail| M[ATHBA repair or tier decision]
    L -->|pass| N[CAS canonical promotion]
    L -->|fail| O[ATHBA regression repair decision]
    N --> P{More fragments?}
    P -->|yes| D
    P -->|no| Q[Complete canonical scenario GREEN]
    Q --> R[Behavior-level review]
```

No model creates intermediate fragment tests.

## Narrow implementation and stronger fallback

```mermaid
stateDiagram-v2
    [*] --> NarrowReady
    NarrowReady --> CodingProfile: ATHBA tier one mapping
    CodingProfile --> CoderSubmission: generic coding small request
    CoderSubmission --> Accepted: deterministic gates clear
    CoderSubmission --> CoderRetry: genuine model failure and submissions remain
    CoderRetry --> CodingProfile
    CoderSubmission --> StrongerProfile: fourth tier-one submission fails
    CoderSubmission --> ExternalBlocked: connector or executor failure
    StrongerProfile --> PrimarySubmission: generic reasoning plus coding medium request
    PrimarySubmission --> Accepted: deterministic gates clear
    PrimarySubmission --> PrimaryRetry: genuine model failure and submissions remain
    PrimaryRetry --> StrongerProfile
    PrimarySubmission --> CapabilityBlocked: fourth tier-two submission fails
    PrimarySubmission --> ExternalBlocked
    Accepted --> [*]
    CapabilityBlocked --> [*]
    ExternalBlocked --> [*]
```

Rack AI sees only the generic profile attached to each submission. ATHBA owns why the profile changed.

## Per-tier identities

```mermaid
flowchart LR
    W[Stable ATHBA work_id] --> T1[Tier 1 generic coding small]
    T1 --> A1[submission_id 1]
    A1 --> A2[submission_id 2]
    A2 --> A3[submission_id 3]
    A3 --> A4[submission_id 4]
    A4 --> X{accepted?}
    X -->|yes| Done[continue TDD]
    X -->|no| T2[Tier 2 reasoning plus coding medium]
    T2 --> B1[new submission_id 1]
    B1 --> B2[new submission_id 2]
    B2 --> B3[new submission_id 3]
    B3 --> B4[new submission_id 4]
    B4 --> Y{accepted?}
    Y -->|yes| Done
    Y -->|no| Block[ATHBA capability blocked]
```

`work_id` is opaque to Rack AI. Every actual invocation has a unique `submission_id` and execution/change identity.

## Capability filtering without software semantics

```mermaid
flowchart TD
    A[Generic job capabilities complexity context] --> B[Registered model profiles]
    B --> C{All required capabilities supported?}
    C -->|no| D[Ineligible: missing generic capability]
    C -->|yes| E{Qualified for complexity?}
    E -->|no| F[Ineligible: complexity envelope]
    E -->|yes| G{Large context satisfied?}
    G -->|no| H[Ineligible: context]
    G -->|yes| I[Eligible worker instances]
    I --> J[Resource and lease filtering]
    J --> K[Generic ranking]
    K --> L[Selection decision]
    L --> M[Execution provenance]
    M --> N{Selected equals executed?}
    N -->|yes| O[Return terminal result]
    N -->|no| P[Fail closed]
```

## Priority is independent of capability

```mermaid
flowchart LR
    A[ATHBA semantic readiness] --> D[Dispatchable]
    B[Required capability set] --> E[Rack AI eligibility]
    C[Low medium high paramount] --> F[Rack AI queue ordering]
    D --> G[Generic job]
    E --> H[Eligible workers]
    F --> I[Scheduling order]
```

A high-priority coding-only job does not become a reasoning job. A low-priority reasoning job remains reasoning work.

## No shared pool and no dependency leakage

```mermaid
sequenceDiagram
    participant A as ATHBA work ledger
    participant C as Rack AI connector
    participant R as Rack AI generic queue
    participant W as Worker

    A->>A: resolve dependencies and readiness
    A->>C: submit ready GenericAiJobRequest
    C->>R: serialize generic job
    R-->>C: queued acknowledgement
    C-->>A: persist submission acknowledgement
    R->>W: select and execute when capacity exists
    W-->>R: terminal execution evidence
    R-->>C: generic result
    C-->>A: correlated result by submission_id
    A->>A: interpret and unlock next internal work
```

Rack AI receives no behavior graph and no instruction that job A must precede job B. ATHBA simply does not submit B until B is ready.

## Replaceable connector

```mermaid
classDiagram
    class AiExecutionPort {
      +submit(job)
      +get_status(submission_id)
      +get_result(submission_id)
      +cancel(submission_id)
    }
    class RackAiConnector
    class FakeAiConnector
    class AlternativeRackConnector
    AiExecutionPort <|.. RackAiConnector
    AiExecutionPort <|.. FakeAiConnector
    AiExecutionPort <|.. AlternativeRackConnector
    class AthbaExecutionProfileResolver
    AthbaExecutionProfileResolver --> AiExecutionPort
```

ATHBA domain services depend on the port, not Rack AI's transport schema.

## Sequential routing proof

```mermaid
sequenceDiagram
    participant A as ATHBA
    participant C as Connector
    participant R as Rack AI

    A->>C: reasoning+coding medium scenario job
    C->>R: generic request
    R-->>A: stronger worker selection and terminal evidence
    A->>A: deterministic scenario decomposition
    A->>C: coding small frontier job
    C->>R: generic request
    R-->>A: coding worker selection and terminal evidence
    A->>A: deterministic GREEN and regression
    A->>C: reasoning+coding medium fallback job
    C->>R: generic request after proven tier exhaustion
    R-->>A: stronger worker selection and terminal evidence
```

This sequential proof is required before any concurrent GPU scheduling test.

## Same model on two GPUs and competing workload

```mermaid
flowchart TD
    MP[Gemma model capability profile: reasoning plus coding] --> W1[Worker instance on 4060 Ti]
    MP --> W2[Worker instance on 4080 Super]
    W1 --> Q[Generic eligible worker set]
    W2 --> Q
    C[ComfyUI lease requests 4080] --> R[Rack AI resource manager]
    R --> W2X[4080 worker temporarily unavailable]
    W1 --> Q2[Remaining eligible reasoning capacity]
```

The detailed lease/scheduler policy is deferred to a separate Rack AI specification. ATHBA's generic job does not change when one worker disappears.

## Resume invariants

Persisted ATHBA state retains:

- internal work identity and development stage;
- generic execution profile used for each submission;
- tier and submissions consumed;
- candidate and no-candidate lineage;
- base ref/SHA and allowed paths;
- connector submission acknowledgement;
- Rack AI selection evidence and execution provenance;
- pending transition receipt;
- canonical revision.

Persisted Rack AI state retains:

- generic request and idempotency key;
- queue/execution status;
- selected worker/resource decision;
- lease evidence;
- terminal packet.

A completed submission, transition, or promotion must not be repeated after restart.
