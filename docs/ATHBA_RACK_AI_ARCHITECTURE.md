# ATHBA + Rack AI Architecture

## Status and authority

This document is the durable product and system boundary for ATHBA and Rack AI.

It supersedes earlier roadmap language that allowed automatic cloud escalation during behavioural execution or semantic replanning. Cloud reasoning is permitted only in explicitly authorised pre-execution design phases. Once a behavioural campaign is sealed, all planning, implementation, testing, review, retry and recovery work is local-only. A local capability failure produces a human-intervention packet; it never triggers an external model call.

## Product goal

ATHBA turns human intent into an approved, technically coherent software-development campaign. Rack AI executes that campaign continuously on the GPU rack through bounded local workers.

The economic design is deliberate:

- use the rack for continuous conversation, specification work, decomposition, implementation, testing, review and recovery;
- use very cheap cloud reasoning only where it materially improves the specification or architecture;
- normally use one explicitly authorised frontier architecture call per approved project specification, and only when the live build policy permits it;
- guarantee zero external-LLM spend after the behavioural campaign is sealed.

## Three-layer system

```text
Layer 1 — Human collaboration and specification
  Local Project Liaison / PM
  Local Technical Specification Builder
  Canonical specification, decisions, questions and approvals

Layer 2 — Architecture and delivery compilation
  Bounded cheap requirements criticism
  Architecture context compilation
  Principal architecture generation
  Architecture audit and approval
  Local delivery decomposition
  Campaign sealing

Layer 3 — Behavioural execution
  Local behaviour planning
  Local Tester / Developer / Reviewer workflows
  Deterministic execution and evidence through Rack AI
  Local retries, splitting and dependency progression
  Completion or human intervention
```

Layer 3 is the work currently exercised by the PR15–PR23 implementation series. Layers 1 and 2 must compile human intent into inputs that this local execution layer can reliably consume.

## Non-negotiable cloud boundary

The decisive transition is `CAMPAIGN_SEALED`.

Before that transition, ATHBA may invoke a configured cloud reasoning gateway only for the design purposes allowed by policy. After that transition:

- ATHBA must not call OpenRouter, OpenAI, Anthropic or any other external LLM provider for the campaign;
- Rack AI must not possess external LLM credentials or external paid-model routes;
- no retry, repair, review, dependency analysis, architecture-conflict handling or unclassified failure may automatically reopen cloud reasoning;
- `local_capability_exhausted`, `blocked_architecture`, `blocked_ambiguity` and equivalent outcomes terminate in `HUMAN_INTERVENTION_REQUIRED`;
- a human may separately decide to edit code, clarify a requirement, revise the architecture or use a subscription/tool outside the autonomous system, but that is a new explicit human action rather than an ATHBA escalation.

The rack may ask for help. It may not reach for the wallet.

## Model policy

ATHBA domain logic depends on capability-oriented gateways, not hard-coded model brands.

Initial development policy:

- the largest suitable rack-hosted model is the default for the Project Liaison and Technical Specification Builder;
- all automated tests use deterministic fake reasoning gateways unless a test is explicitly marked as a live-model proof;
- the single configured cloud development model is DeepSeek V4 Flash through OpenRouter, exposed behind a provider-neutral `ReasoningGateway`;
- during ordinary feature development, DeepSeek also stands in for the future principal architect so development does not repeatedly incur frontier-model costs;
- only the first small number of real end-to-end application builds may use an explicitly authorised frontier architect call as a live acceptance proof;
- model IDs, providers, token limits and budgets are configuration. They are not embedded in specification, architecture or execution-domain records.

A future local multi-GPU model spanning the RTX 4080 Super and RTX 4060 Ti may be evaluated as an additional Rack AI-managed local capability before human intervention. ATHBA may request a capability class but may never select those cards, a model process or a worker directly.

## ATHBA ownership

ATHBA is the software-development product and development-domain control plane. It owns:

- project-facing conversation and activity history;
- canonical specification versions;
- requirements, assumptions, decisions and open questions;
- product and technical approvals;
- architecture context compilation;
- cloud-call authorisation and cost policy during permitted design phases;
- architecture bundles and architecture decisions;
- decomposition into human stories, behaviour contracts and machine work;
- campaign sealing and traceability;
- software-development progression, TDD semantics and human-intervention packets;
- project environments, runtime/toolchain/dependency meaning and build/test command meaning.

ATHBA must not own physical GPU, worker or local-model placement.

## Rack AI ownership

Rack AI is the rack-wide execution and resource control plane. It owns:

- rack-wide resource arbitration;
- local GPU, model and worker selection;
- model/service lifecycle and leases;
- JCode-backed bounded execution;
- host or isolated workspace execution according to administrator policy;
- trusted worktrees and accepted-revision progression;
- allowed-path, command, timeout, resource and network enforcement;
- deterministic acceptance execution and evidence capture;
- generic local retry/resource policy within the submitted campaign contract.

Rack AI receives no cloud key and exposes no external paid-model fallback.

ATHBA may describe complexity, capability and context needs. Rack AI decides how local resources satisfy them.

## Layer 1: human-facing control plane

The normal user interacts with a Project Liaison presented as the project manager. It explains state, presents questions, records answers, requests approvals and reports progress. It is not authorised to invent requirements, architecture or project facts.

A logically separate Technical Specification Builder elicits and normalises product intent. It maintains a canonical, versioned specification rather than relying on conversation memory. The same local model endpoint may initially serve both roles, but each role has an isolated prompt, tool set, state transition contract and output schema.

The source of truth is persisted project state:

- `SpecificationVersion`;
- stable requirement identifiers;
- `DecisionRecord`;
- `AssumptionRecord`;
- `OpenQuestion`;
- `ApprovalRecord`;
- immutable activity/evidence references.

Conversation is an interface to that state, not the state itself.

## Layer 2: architecture and compilation

An approved specification moves through a bounded design pipeline:

```text
Canonical specification
  -> cheap requirements criticism and human clarification
  -> product and technical approval
  -> authoritative architecture dossier
  -> principal architecture generation
  -> architecture validation/audit
  -> human architecture approval where required
  -> local delivery decomposition
  -> sealed behavioural campaign
```

The architecture call receives a compiled, authoritative dossier rather than every historical transcript. Its output is a structured `ArchitectureBundle`, not an untyped essay.

The local Delivery Decomposer converts the approved bundle into a dependency graph of deliberately bounded behavioural work. Every resulting item retains traceability to source requirements and architecture decisions and includes machine-verifiable acceptance expectations.

If the local decomposer cannot produce valid bounded work, ATHBA stops for human intervention before sealing. It does not silently ask a stronger model.

## Layer 3: local behavioural execution

A sealed campaign is handed to the existing ATHBA -> Rack AI execution architecture. The behavioural layer owns progression from approved behaviour down through strict TDD microcycles, deterministic evidence, semantic review, accepted revisions and final specification reconciliation.

The intended outcome is not that a small model understands the whole application repeatedly. The intended outcome is that the hard product and architectural decisions have already been compiled into sufficiently narrow, independently checkable work.

Local execution may:

- retry within explicit bounds;
- split work within the approved semantic objective;
- reorder dependency-ready work;
- use any Rack AI-selected local capability allowed by administrator policy;
- continue unrelated ready work while one branch is blocked;
- produce a complete human handoff when autonomy is exhausted.

It may not alter product intent or architecture to make code pass.

## Approval and versioning rules

A project progresses by immutable versioned artefacts.

Product approval confirms that the specification describes the intended product and observable outcomes. Technical approval confirms that constraints, quality attributes and material technical assumptions are sufficiently clear for architecture.

Architecture generation and campaign sealing reference exact versions and content hashes. A material later change creates a new specification or architecture version. It never mutates the meaning of an already sealed campaign invisibly.

## Primary integration artefacts

The intended cross-stage artefacts are:

- `CanonicalSpecification` — approved product and technical intent;
- `ArchitectureDossier` — compiled authoritative input to the architect;
- `ArchitectureBundle` — structured architecture and traceability output;
- `BehaviouralCampaignGraph` — dependency-aware human and machine delivery plan;
- `CampaignPackage` — immutable sealed input to local execution;
- `ExecutionReport` — accepted revisions, evidence, outcomes and blockers;
- `HumanInterventionPacket` — exact diagnosis and evidence when local autonomy stops.

Schemas and names may evolve during implementation, but the authority and cost boundaries above must not.

## Frontend boundary

The frontend is a client of ATHBA application services. It must not contain hidden agent state, provider credentials or development progression logic.

Django remains the authoritative backend during the migration. A richer TypeScript frontend may be introduced behind explicit APIs and event streams, but the choice of browser framework must remain separate from the agent and architecture contracts.

## Delivery sequence

The next planning PRs divide the remaining product into independently reviewable concerns:

1. local Project Liaison and Technical Specification Builder control plane;
2. collaborative project workspace and frontend modernisation;
3. bounded cloud architecture pipeline, local delivery decomposition and campaign sealing;
4. completion and live validation of the existing behavioural-ticket-down stack;
5. later integration/release, richer repository intelligence and safe local concurrency.

## Design principle

ATHBA is a compiler from human intent to locally executable evidence-bearing work:

```text
Human intent
  -> canonical specification
  -> approved architecture
  -> behavioural dependency graph
  -> sealed local campaign
  -> code, tests and evidence
```

Models propose typed artefacts. Persisted, versioned and validated artefacts are authoritative. Cloud intelligence may help compile the contract; it cannot rescue the execution.