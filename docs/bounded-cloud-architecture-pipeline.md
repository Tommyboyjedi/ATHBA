# Bounded Cloud Architecture and Local Delivery Compilation

## Status

Documentation-only architecture and implementation contract for ATHBA's middle layer.

This PR depends on PR24 for the canonical specification, Project Liaison, Technical Specification Builder and approval records. It hands a sealed delivery package to the behavioural-ticket-down architecture being implemented and proven in PR15–PR23.

No runtime code, API integration or paid model call is included in this PR.

## Goal

Turn one approved `ARCHITECTURE_READY` specification into a detailed, traceable architecture and then compile that architecture locally into bounded component requirements suitable for ATHBA's local Behavior Planner, Tester, Developer, Reviewer and Rack AI execution path.

The design must concentrate paid intelligence into a very small pre-execution window and make the following guarantee:

> Once the package submitted to the local Behavior Planner is sealed, ATHBA and Rack AI make no external LLM calls for that campaign. Local failure ends in human intervention, not cloud escalation.

## Pipeline

```text
Approved CanonicalSpecification
  -> Requirements Critic
  -> Human clarification through Project Liaison
  -> repeat cheap criticism only within explicit cap
  -> Product and Technical approval confirmation
  -> Architecture Context Compiler
  -> Principal Architect
  -> Architecture validation and cheap audit
  -> Human architecture decision where required
  -> Local Delivery Decomposer
  -> Campaign validation
  -> CAMPAIGN_SEALED
  -> Local Behavior Planner
  -> Local strict TDD / implementation / review through Rack AI
  -> Complete or HUMAN_INTERVENTION_REQUIRED
```

There is no transition from the local execution states back to Requirements Critic, Principal Architect or any other cloud role.

## Core decisions

1. OpenRouter is the initial production gateway for permitted cloud design calls, behind ATHBA's provider-neutral `ReasoningGateway`.
2. During development, one cheap model alias is sufficient. Both cheap review and principal-architect test roles resolve to DeepSeek V4 Flash so the pipeline can be built and exercised without repeated frontier-model expense.
3. Automated and CI tests use deterministic fake gateways. Live DeepSeek calls are opt-in integration proofs with strict token and spend caps.
4. Frontier architecture generation is not part of ordinary feature development. It is enabled only for the first small number of real end-to-end application builds, expected initially to be one to three, and only through explicit human authorisation.
5. The normal live-product path expects one principal architecture request for one approved specification version.
6. No model fallback, provider auto-routing or automatic retry may silently increase spend.
7. The Architecture Context Compiler sends an authoritative, de-duplicated dossier rather than every transcript and draft.
8. The Principal Architect returns a typed `ArchitectureBundle`, not an unstructured essay.
9. Delivery decomposition is a local ATHBA responsibility. It does not invoke a cloud model.
10. The campaign seal sits immediately before the existing local Behavior Planner path.
11. Rack AI never receives an OpenRouter or other cloud credential.
12. Any post-seal ambiguity, architecture conflict or model-capability exhaustion produces a durable human-intervention packet.

## Development model policy

### Capability aliases

Domain/application code addresses roles through policy aliases, for example:

```text
cheap_design_reasoner
principal_architect
architecture_auditor
local_delivery_decomposer
```

Model IDs are configuration, not domain data.

### Initial development mapping

The initial external mapping is:

```text
cheap_design_reasoner  -> deepseek/deepseek-v4-flash-0731 via OpenRouter
principal_architect    -> deepseek/deepseek-v4-flash-0731 via OpenRouter
architecture_auditor   -> deepseek/deepseek-v4-flash-0731 via OpenRouter
```

The exact provider/model identifier may be updated in configuration if availability or price changes. The architectural invariant is that ordinary development uses the one inexpensive configured model as a stand-in for the eventual role mix.

### Test modes

The implementation must distinguish:

```text
FAKE
LOCAL_LIVE
CHEAP_CLOUD_LIVE
FRONTIER_LIVE
```

- `FAKE` is the default for unit, component and CI tests.
- `LOCAL_LIVE` may prove the local Delivery Decomposer and later local execution.
- `CHEAP_CLOUD_LIVE` invokes the configured DeepSeek model and requires an explicit test marker plus a hard budget.
- `FRONTIER_LIVE` is disabled by default and is permitted only under the live-application proof policy.

A test cannot switch mode because a fake or local result failed.

## First live application policy

The first one to three real applications produced end to end through ATHBA and Rack AI are the acceptance tests for the complete architecture.

For each approved application specification:

- requirements criticism may use the cheap configured DeepSeek role within its call/spend cap;
- architecture-development rehearsals continue to use DeepSeek;
- the human may explicitly authorise one frontier principal-architect request when the dossier is ready;
- the authorisation screen records the exact specification/dossier hash, resolved model, provider policy, estimated input, maximum output and maximum charge;
- no automatic retry occurs after timeout, transport failure, invalid schema or disappointing content;
- a second request requires a new explicit human decision and a recorded reason; it is not part of the normal success path;
- the returned bundle and usage record become immutable evidence for evaluating whether the expensive call was worthwhile.

After these live builds, the evidence should be reviewed before establishing the long-term production model policy. This PR does not require a model bake-off before implementation begins.

## Permitted cloud purposes

The bounded design gateway accepts only typed purposes:

```text
REQUIREMENTS_CRITIQUE
PRINCIPAL_ARCHITECTURE
ARCHITECTURE_AUDIT
```

It does not expose an arbitrary prompt endpoint to the browser or general ATHBA workflows.

It must reject calls for:

- Behavior Planner work;
- test design after campaign seal;
- Developer repair;
- code review during execution;
- dependency repair during execution;
- unclassified local failures;
- local resource or model failure;
- generic chat;
- any purpose not explicitly allowlisted by design-phase policy.

## Requirements Critic

### Responsibility

The Requirements Critic challenges the specification before the principal architecture request. It is not the final architect and cannot approve its own findings.

It should identify:

- contradictions;
- missing actors or journeys;
- undefined failure behaviour;
- untestable acceptance criteria;
- hidden assumptions;
- incomplete data ownership, sensitivity or retention facts;
- missing integration contracts;
- security, privacy, accessibility, performance and operational gaps;
- conflicts among budget, deployment and technology constraints;
- product choices incorrectly presented as technical implementation questions;
- technical decisions incorrectly delegated to a nontechnical product owner;
- questions whose answers would materially alter architecture.

### Output

A `RequirementsCritique` contains:

```text
critique_id
specification_version
specification_hash
findings[]
questions[]
non_blocking_observations[]
coverage_summary
model_invocation_ref
```

Each finding includes:

```text
finding_ref
category
severity
source_refs
statement
why_it_matters
recommended_disposition
blocking
confidence
```

Each question follows the PR24 `OpenQuestion` contract and enters the canonical project state only after deterministic validation.

### Iteration policy

The workflow may perform several cheap critique rounds because the cost is low and the questions may substantially improve the one architecture request. It remains bounded by configuration such as:

```yaml
requirements_critique:
  model_alias: cheap_design_reasoner
  max_calls_per_specification_version: 6
  max_total_input_tokens: 400000
  max_total_output_tokens: 60000
  max_spend_usd: 0.25
  automatic_provider_fallback: false
```

These values are initial ceilings, not expected spend and not immutable product constants.

The Project Liaison presents accepted questions to the human. Answers create a new specification version where material. The critic never edits an approved version in place.

The workflow stops criticism when:

- no blocking material findings remain;
- the call cap or budget is reached;
- the human elects to proceed with explicitly accepted risks;
- the critic returns an invalid/untrustworthy result and the human declines another call.

## Approval gate before architecture

The Principal Architect receives only a specification version that has:

- deterministic schema and traceability validation;
- no unresolved blocking questions, unless a human has explicitly accepted and recorded the risk;
- product approval for the exact hash;
- technical approval for the exact hash;
- a complete source manifest;
- an architecture-request state that has not already consumed the permitted principal result.

A later material change produces a new version and returns to the relevant review/approval stages.

## Architecture Context Compiler

### Responsibility

The Architecture Context Compiler is deterministic/local application code. It builds the highest-signal authoritative dossier that fits the configured principal model and cost boundary.

It does not ask an LLM to decide what the current truth is.

### Dossier contents

The `ArchitectureDossier` should contain ordered sections equivalent to:

1. executive architectural brief;
2. approved canonical specification;
3. actors, journeys and acceptance outcomes;
4. prioritised quality attributes;
5. constraints and explicit non-goals;
6. decision and assumption register;
7. data classification, ownership and lifecycle requirements;
8. integration inventory and known contracts;
9. deployment/runtime/operational constraints;
10. security and trust requirements;
11. current repository/system map for brownfield work;
12. relevant existing schemas, interfaces and source excerpts;
13. applicable engineering principles and fixed architecture boundaries;
14. rejected approaches and reasons;
15. unresolved non-blocking risks;
16. required `ArchitectureBundle` output schema and completion rules;
17. source/version/hash manifest.

### Brownfield repository dossier

For an existing application, the compiler should derive a repository packet containing:

- tree and module/package map;
- build, test and deployment commands;
- dependency inventory;
- database/data schemas;
- exposed APIs/events;
- component ownership where known;
- existing architectural decisions;
- test topology;
- selected architecturally significant source excerpts;
- known technical debt relevant to the requested change.

Raw source is included only when it materially affects architecture. Duplicated generated files, dependency caches, logs and irrelevant history are excluded.

### Compilation rules

The compiler must:

- include only authoritative current versions by default;
- mark historical/superseded material unmistakably when included for rationale;
- de-duplicate repeated content;
- preserve stable requirement and decision IDs;
- identify omissions rather than fill them with guesses;
- estimate tokens before dispatch;
- fail closed when required sections or hashes are missing;
- persist the exact dossier bytes/hash sent to the model.

## Principal Architect

### Responsibility

The Principal Architect creates a complete architecture suitable for subsequent local delivery decomposition. It is the high-leverage reasoning stage, not a conversational coding agent.

It must reason over the whole authorised dossier and produce explicit choices, boundaries, contracts and trade-offs. It must not assume that later small local models can recover missing architecture from broad prose.

### Legal outcomes

```text
COMPLETE
BLOCKED_BY_MATERIAL_AMBIGUITY
INVALID
```

`BLOCKED_BY_MATERIAL_AMBIGUITY` identifies the exact missing decisions and affected requirements. It does not invent an answer to preserve the one-call appearance of success.

`INVALID` is assigned by ATHBA when the response cannot be parsed, references the wrong dossier/specification hash or violates mandatory schema rules.

### ArchitectureBundle

The returned `ArchitectureBundle` is a versioned aggregate containing at least:

#### Manifest

- project id;
- specification version/hash;
- dossier version/hash;
- architecture version;
- model invocation identity;
- generation timestamp;
- schema version;
- overall status.

#### Executive architecture

- concise solution shape;
- architectural goals;
- primary trade-offs;
- fixed constraints;
- major risks.

#### System context and decomposition

- systems/actors/external dependencies;
- containers/services/applications;
- components/modules;
- ownership and responsibility boundaries;
- permitted dependency directions;
- stateful/stateless boundaries.

#### Domain and data architecture

- domain concepts and invariants;
- aggregate/ownership boundaries where relevant;
- persistence choices and rationale;
- schema/data-contract definitions;
- data lifecycle, retention and deletion;
- migration and compatibility requirements;
- consistency and concurrency rules.

#### Interfaces and workflows

- APIs, commands, events and integrations;
- request/response and error contracts;
- idempotency and versioning;
- state machines and critical sequences;
- authentication/authorisation boundaries;
- failure and retry behaviour.

#### Quality attributes

- security and threat controls;
- privacy/data protection;
- accessibility;
- performance and capacity;
- availability/resilience;
- observability/audit;
- maintainability and extensibility;
- deployment and operations.

#### Delivery guidance

- component-level implementation boundaries;
- dependency ordering;
- safe incremental slices;
- test strategy and acceptance layers;
- migration/release strategy;
- work that must remain human-reviewed;
- explicit constraints the local development layer may not change.

#### Decisions and alternatives

- ADR-equivalent decisions;
- alternatives considered;
- reasons for rejection;
- consequences;
- assumptions and confidence.

#### Traceability

- every source requirement mapped to one or more architecture elements;
- every architecture constraint linked to its source or rationale;
- explicit unmapped requirements or unexplained elements;
- risk/decision references.

The bundle may render human-readable Markdown and diagrams, but the typed records remain authoritative.

## Architecture validation

Before any audit or decomposition, deterministic validation checks:

- schema validity;
- specification and dossier hash match;
- stable unique identifiers;
- no missing mandatory sections;
- requirement-to-architecture mapping coverage;
- internal reference integrity;
- dependency cycles where structurally detectable;
- ownership collisions;
- interface endpoints/events referencing defined components;
- decisions referencing valid sources;
- explicit representation of unresolved risks;
- no physical Rack AI GPU/model/worker selection embedded in the architecture.

Mechanical validation failure does not trigger an automatic second architecture request.

## Architecture Auditor

The Architecture Auditor performs a focused independent challenge using the cheap configured model during the permitted design phase.

It should test for:

- uncovered requirements;
- contradictory component ownership;
- undefined trust boundaries;
- incomplete failure paths;
- unrealistic local-delivery assumptions;
- missing migration/operational detail;
- architecture that cannot be divided into bounded behaviour;
- requirements whose acceptance cannot be demonstrated;
- hidden decisions not recorded as ADRs;
- accidental coupling to a named cloud provider, GPU or worker.

The auditor returns findings only. It does not silently rewrite the bundle.

Findings are resolved by one of:

- deterministic correction of representation without changing meaning;
- human-authored architecture amendment;
- human acceptance of a non-blocking risk;
- return to specification clarification/versioning;
- explicit human authorisation of another principal request in an exceptional case.

There is no automatic frontier repair loop.

## Architecture approval

Projects may configure whether architecture approval is always required or required only above defined risk/size thresholds. The first live application proofs should require explicit human architecture approval.

Approval binds to the exact `ArchitectureBundle` version/hash and records unresolved accepted risks.

Approval means the architecture is authorised for delivery compilation. It does not claim that every future implementation attempt will succeed.

## Local Delivery Decomposer

### Position and cost rule

The Delivery Decomposer is the final middle-layer role and runs locally. It sits after approved architecture and before campaign sealing.

It may use the largest suitable Rack AI-managed local model, deterministic parsing and repeated local validation. It has no cloud route.

### Responsibility

It compiles the architecture into a dependency-aware `BehaviouralCampaignGraph` whose leaf inputs are suitable for the existing local Behavior Planner and Specification Gatekeeper paths.

It should produce component-level requirements, not final code patches and not necessarily final test source. PR17/PR23 retain responsibility for turning each component requirement into Behavior Contracts, independent Gatekeeper obligations and strict TDD scenario microcycles.

### Output hierarchy

```text
ArchitectureBundle
  -> delivery capabilities / epics
  -> human stories
  -> component-level architectural requirements
  -> local Behavior Planner input
  -> Behavior Contracts and strict scenarios (existing layer)
  -> DevelopmentWorkUnits / Rack AI execution (existing layer)
```

### Component requirement contract

Each local Behavior Planner input contains at least:

```text
component_requirement_ref
story_ref
objective
observable_behaviour
source_requirement_refs
architecture_element_refs
architecture_decision_refs
dependencies
allowed semantic scope
known repository/component scope
interface/data contracts
architecture constraints
quality/acceptance obligations
non_goals
required evidence categories
risk and human-review flags
context references
```

It must not include a provider/model/GPU/worker selection.

### Decomposition rules

The local decomposer must:

- preserve source and architecture traceability;
- separate unrelated behaviours;
- make dependencies explicit;
- avoid asking the Behavior Planner to choose unresolved architecture;
- keep a unit within configured semantic/context complexity limits;
- identify cross-cutting obligations that must be tested/reconciled across components;
- distinguish human stories from machine work;
- preserve migration/integration steps;
- avoid duplicating the same obligation under multiple independent refs;
- output deterministic identifiers or identifier seeds that survive retry;
- stop with a typed blocker when safe decomposition is impossible.

It may recursively split locally, but split recursion and attempts remain bounded.

### Admission checks before sealing

A component requirement is not admitted when it contains:

- unresolved product meaning;
- an unmade architecture choice;
- contradictory interface definitions;
- undefined dependencies;
- acceptance obligations with no plausible evidence route;
- context that exceeds the configured local Behavior Planner envelope and cannot be referenced/retrieved safely;
- multiple unrelated behavioural objectives;
- authority to weaken architecture or tests;
- a requirement for a cloud call during execution.

A failed admission produces a local decomposition blocker for human review. It does not invoke DeepSeek automatically.

## CampaignPackage and seal

The validated graph is materialised as an immutable `CampaignPackage` containing:

```text
campaign_id
project_id
specification_version/hash
architecture_version/hash
decomposition_version/hash
repository/environment binding
human stories
component requirements
dependency graph
global architecture invariants
quality and acceptance policy
allowed local capabilities
retry/split bounds
human review policy
execution evidence requirements
cloud_policy: DENIED
schema/version manifest
```

The package hash covers all authoritative inputs and policy fields.

`CAMPAIGN_SEALED` requires:

- current product/technical approvals still match the specification hash;
- architecture is valid and approved where required;
- all admitted component requirements pass local validation;
- dependency graph is acyclic or contains only explicitly supported orchestration cycles;
- repository and environment identity exist;
- no cloud-purpose field or external model route exists in the execution payload;
- the human is shown the campaign summary and seal action when project policy requires it.

After sealing, any material modification creates a new campaign version. The sealed package is never edited in place.

## Hard enforcement after seal

The no-cloud rule must be enforced by construction:

- Rack AI processes/services receive no OpenRouter/OpenAI/Anthropic credential;
- local execution containers/workspaces receive no such credential;
- the Behavior Planner, Specification Gatekeeper, Tester, Developer and Reviewer gateway interfaces expose only local capability requests;
- the post-seal state machine contains no transition to a cloud design purpose;
- a runtime network policy may deny external model endpoints in execution environments;
- an audit test scans execution configuration and serialized packages for forbidden provider/model/fallback fields;
- cloud usage ledger must remain unchanged for the campaign after the seal timestamp.

A prompt saying `do not use cloud` is not sufficient enforcement.

## Integration with PR17 and PR23

The existing behavioural stack begins from a component-level requirement and independently sends it to:

- the Behavior Planner, which creates bounded behaviour contracts/scenarios;
- the Specification Gatekeeper, which creates independent atomic obligations for later evidence reconciliation.

This PR's local Delivery Decomposer must produce that common source input and preserve its requirement/architecture references. It must not pre-share Gatekeeper output with the Behavior Planner or collapse their independence.

PR23's strict TDD frontier semantics, accepted-revision progression, persistence/resume and evidence remain authoritative below this boundary. This PR adds no alternate execution engine.

## Post-seal failure policy

Local execution may use all locally available methods authorised by Rack AI policy, including future higher-capability local roles. It may retry, split, re-order and continue independent branches within existing semantic constraints.

When it cannot proceed, it emits `HUMAN_INTERVENTION_REQUIRED` with a `HumanInterventionPacket` containing:

```text
campaign/package identity
story/component/behaviour/work refs
last semantically trusted revision
failure classification
actions attempted and bounds consumed
local model/reviewer diagnoses as evidence
relevant diffs and candidate refs
tests/commands/stdout/stderr
architecture and requirement refs involved
unblocked work that may continue
exact unresolved question or repair need
permitted human resolutions
confirmation that post-seal cloud usage is zero
```

Examples include:

- product ambiguity discovered despite approval;
- architecture contradiction;
- local decomposer/Behavior Planner gap not safely recoverable;
- repeated implementation defect beyond local bounds;
- missing project environment/toolchain;
- local model capability exhaustion;
- unclassified evidence.

The packet may be used by the human with their own judgement, ChatGPT subscription, Codex, Grok, work tooling or manual coding. Those actions are outside the autonomous cloud budget. ATHBA records the resulting patch, clarification or revised artefact only when the human explicitly submits it.

## Explicit re-entry, never automatic escalation

A human response may:

- provide a manual code change and resume from a reviewed trusted revision;
- clarify a requirement and create a new specification version;
- amend an architecture decision and create a new architecture/campaign version;
- change local infrastructure/model policy;
- abandon or defer the work.

Only the human can initiate a new design-phase cloud request. A blocker alone cannot do so.

## OpenRouter adapter requirements

The first production adapter should support:

- exact model allowlisting;
- provider routing constrained by policy;
- disabled model fallback unless explicitly configured for a design phase;
- maximum provider price and total estimated request cost checks;
- input/output/reasoning token limits;
- Zero Data Retention/data-policy constraints where configured;
- request idempotency/correlation;
- usage and actual-cost capture;
- raw response/evidence retention according to project data policy;
- timeout/cancellation without automatic paid retry;
- typed purpose and response-schema validation.

If a cheaper direct provider later becomes preferable, a new adapter may implement the same `ReasoningGateway`. No domain or workflow change should be required.

## Cloud call ledger

Every permitted call records:

```text
invocation_id
project_id
purpose
specification/dossier/architecture refs and hashes
model alias and resolved model/provider
policy version
estimated tokens and maximum charge
human authorisation ref where required
request timestamp
response status
actual token usage
actual charge
response/evidence refs
```

The ledger supports project/phase spend caps and demonstrates that execution spend remains zero.

## Security and data handling

The dossier compiler should minimise and classify data before external transmission.

Rules include:

- never send provider credentials in prompts or persisted model artefacts;
- redact secrets and live personal/clinical/customer records;
- prefer schemas, representative fixtures and data classifications over production data;
- record which source artefacts were transmitted;
- apply provider retention/training policy explicitly;
- keep cloud credentials only in the bounded ATHBA design service;
- prevent browser access to the credential;
- prevent Rack AI and target workspaces from inheriting it.

## Future local multi-GPU experiment

The arrival of the RTX 4080 Super creates a future experiment: evaluate whether a larger model spread across the RTX 4080 Super and RTX 4060 Ti provides useful high-capability local reasoning before human intervention.

That experiment is intentionally outside this PR. Its architectural constraints are:

- Rack AI owns model loading, placement and resource policy;
- ATHBA requests a local capability class, not named GPUs;
- cross-GPU performance, memory overhead, interconnect limitations and reliability must be measured on real ATHBA tasks;
- success may add another local tier before human intervention;
- failure does not create a cloud fallback;
- the sealed campaign and zero-spend execution invariant remain unchanged.

## Implementation sequence

1. Define typed design purposes, model aliases, invocation records and budget policy.
2. Implement deterministic fake `ReasoningGateway` and policy tests.
3. Add the OpenRouter adapter for the single configured DeepSeek development model.
4. Implement Requirements Critic schema/workflow against fake responses.
5. Integrate clarification questions with PR24 project state.
6. Implement Architecture Dossier compilation and token/cost preflight.
7. Implement Principal Architect invocation and `ArchitectureBundle` parsing against fakes.
8. Add deterministic architecture validation.
9. Implement the cheap Architecture Auditor as findings-only.
10. Implement architecture approval/versioning.
11. Implement the local Delivery Decomposer behind a local reasoning interface.
12. Compile component requirements compatible with the PR17/PR23 entry contract.
13. Implement `CampaignPackage`, validation and cryptographic/content sealing.
14. Prove no post-seal cloud route or credential exists.
15. Run opt-in DeepSeek integration proofs.
16. Use a frontier model only during the explicitly authorised first real application build(s).

Implementation should be split further if a single PR would combine provider plumbing, architecture schemas and local decomposition into an unreviewable change.

## Required deterministic tests

The implementation series must prove at least:

- unapproved or mismatched specification versions cannot enter architecture;
- the critic produces typed findings/questions and cannot mutate approved state directly;
- critique call count, token and spend caps are enforced;
- only allowlisted design purposes can reach the cloud gateway;
- model/provider fallback is disabled by default;
- unit/CI tests use fakes and cannot unexpectedly spend money;
- dossier compilation is deterministic for the same authoritative inputs;
- superseded drafts and unrelated transcripts are excluded;
- dossier/specification hashes are verified on the architecture response;
- invalid architecture output cannot advance;
- every requirement has explicit traceability or a visible unmapped finding;
- auditor findings cannot silently rewrite architecture;
- one principal-architect result policy and explicit reauthorisation are enforced;
- the local Delivery Decomposer has no cloud gateway dependency;
- component requirements do not contain unresolved architecture decisions;
- the resulting input preserves Gatekeeper/Behavior Planner independence;
- campaign validation rejects provider keys, cloud purposes and physical GPU/model/worker selectors;
- sealed packages are immutable and versioned;
- no post-seal state transition reaches cloud design;
- post-seal cloud ledger usage remains unchanged;
- execution failure creates a complete human-intervention packet;
- human resolution is explicit and idempotent;
- existing behavioural-stack tests remain green when integration is implemented.

## Opt-in live proof sequence

### Cheap model development proof

Using a disposable approved specification:

1. run one DeepSeek Requirements Critic call;
2. persist usage/cost and typed findings;
3. resolve at least one question into a new version;
4. compile the architecture dossier;
5. run DeepSeek as the stand-in Principal Architect;
6. validate and audit the bundle;
7. run the local Delivery Decomposer;
8. seal a campaign;
9. prove attempts to invoke cloud after sealing are rejected before transport;
10. submit one component requirement to the local behavioural entry path.

### First real application proof

For each authorised live application:

1. complete the approved specification and dossier;
2. show the human the exact frontier-call cost preflight;
3. obtain explicit authorisation;
4. make the principal architecture request once on the normal path;
5. persist the exact dossier, response, usage and cost;
6. validate/audit and obtain required architecture approval;
7. decompose locally and seal;
8. build from the Behavior Planner down using local compute only;
9. record every intervention and verify post-seal external-model cost is exactly zero;
10. evaluate the quality and value of the principal call after completion.

## Non-goals

This PR does not:

- select the eventual permanent frontier architect model;
- run a broad model bake-off;
- permit automatic cloud execution fallback;
- implement the Project Liaison or specification UI;
- redesign PR23 strict TDD microcycles;
- place models on GPUs;
- implement the future 4080 Super plus 4060 Ti model-spreading experiment;
- promise that every possible local ticket will complete without human help;
- allow the browser to submit arbitrary cloud prompts;
- make the architect produce final per-attempt coding prompts.

## Definition of done

The future implementation is complete when one approved specification can pass through bounded cheap review, a controlled principal architecture request, deterministic validation, independent audit, local delivery decomposition and immutable campaign sealing; the resulting component requirements enter the existing local Behavior Planner/Gatekeeper path with full traceability; development tests incur no accidental frontier expense; and every post-seal code, test, review, retry and failure path is structurally unable to call an external LLM.