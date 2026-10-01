# Front-Facing Agent Control Plane

## Status

Documentation-only implementation contract for the first layer of the future ATHBA product.

This PR does not implement a new user interface, cloud architecture generation or Rack AI execution. It defines the authoritative backend behaviour that those later slices must consume.

## Goal

Create a local, persistent project-intake and specification workflow in which a human can describe an application conversationally, refine it over several sessions, understand what remains unclear and approve an exact specification version for architecture.

The human should normally experience one coherent project conversation. Internally, ATHBA separates the responsibilities of the Project Liaison and the Technical Specification Builder so that friendly conversation cannot silently become product authority.

## Core decisions

1. Both front-facing reasoning roles run on local rack-hosted models by default.
2. The initial capability target is the largest suitable local model available through Rack AI, expected initially to be the Gemma-class primary model.
3. Conversation history is not the source of truth. Persisted typed project artefacts are authoritative.
4. The Project Liaison communicates and coordinates; it does not invent or approve requirements.
5. The Technical Specification Builder elicits and normalises intent; it does not select implementation architecture.
6. Product and technical approval are separate recorded decisions against an immutable specification version.
7. No cloud provider credential or call is required anywhere in this layer.
8. The handoff to architecture occurs only when deterministic completeness checks and the required human approvals pass.

## Roles

### Project Liaison

The Project Liaison is presented to the user as the project manager. Its job is to make the whole product feel coherent even when several specialist workflows operate behind it.

It may:

- welcome the user and create or select a project;
- explain the current project state in plain language;
- capture high-level ideas and route them into specification elicitation;
- present clarification questions produced by the Technical Specification Builder or later architecture stages;
- translate technical questions into language appropriate for the current user without changing their meaning;
- summarise proposed specification changes before committing them;
- request product approval and technical approval from the configured approvers;
- report architecture, campaign and execution status from persisted state;
- present human-intervention packets and explain the next human decision required.

It must not:

- infer that a requirement is approved merely because it appeared in chat;
- resolve contradictions without recording the decision;
- select databases, frameworks, deployment patterns or other architecture;
- alter approved artefacts silently;
- claim that work is complete without accepted state/evidence;
- use its model context as durable memory;
- call a cloud model.

Every material user statement must either be recorded as an artefact proposal, linked to an existing artefact, or retained only as non-authoritative conversation.

### Technical Specification Builder

The Technical Specification Builder is a specialist elicitation and normalisation role. It may be surfaced through the Project Liaison rather than addressed directly by most users.

It owns the process of converting vague intent into a structured `CanonicalSpecification` candidate.

It must:

- classify new information as requirement, constraint, quality attribute, assumption, decision, non-goal, acceptance criterion or open question;
- assign stable identifiers;
- preserve source references to the user statement or imported document that caused an artefact to be proposed;
- detect direct contradictions and incomplete definitions;
- ask bounded batches of high-value questions;
- provide sensible defaults only as explicit proposals with consequences;
- distinguish facts the user can decide from technical choices that belong to architecture;
- create a new immutable specification version when a reviewable revision is produced;
- provide plain-language and technical views over the same underlying artefacts;
- refuse to mark a specification architecture-ready while blocking questions or required approvals remain.

It must not:

- write a solution architecture;
- fabricate integrations, actors, data sources or compliance needs;
- treat a local model judgement as human approval;
- overwrite previous versions;
- call a cloud model.

## Shared local model, isolated authorities

The first implementation may use one local model endpoint for both roles. That does not make them one agent.

Each role requires:

- a distinct system prompt;
- a distinct tool allowlist;
- a distinct structured response schema;
- an explicit state-transition contract;
- independent audit identity in project history;
- no ability to execute the other role's privileged commands.

The Project Liaison may request a specification operation through an application service. It may not directly mutate specification persistence. The Technical Specification Builder may propose a change set, but application code validates and commits that change set.

## Authoritative domain artefacts

The implementation should introduce or evolve typed records equivalent to the following.

### `ProjectRecord`

- project id;
- name and optional description;
- lifecycle state;
- active specification version;
- active architecture version, when one exists;
- current campaign identity, when one exists;
- configured product and technical approvers;
- creation/update audit metadata.

### `SpecificationVersion`

- immutable version id and ordinal;
- project id;
- parent version id;
- status;
- exact content hash;
- included requirement/decision/assumption/question references;
- source manifest;
- created-by identity and timestamp;
- supersession relationship.

Suggested statuses:

```text
DRAFT
ELICITING
REVIEW_READY
PRODUCT_APPROVAL_PENDING
TECHNICAL_APPROVAL_PENDING
ARCHITECTURE_READY
SUPERSEDED
WITHDRAWN
```

### `RequirementRecord`

- stable ref such as `REQ-F-001` or `REQ-NFR-004`;
- title and statement;
- category;
- rationale;
- priority;
- acceptance criteria;
- source evidence refs;
- affected actors/data/workflows;
- status and revision lineage.

### `DecisionRecord`

- stable `DEC-*` ref;
- question or choice decided;
- selected option;
- alternatives considered;
- consequences;
- decision authority;
- source evidence;
- effective specification version.

### `AssumptionRecord`

- stable `ASM-*` ref;
- assumption statement;
- confidence/source;
- validation owner;
- impact if false;
- blocking/non-blocking status;
- disposition.

### `OpenQuestion`

- stable `QUE-*` ref;
- exact question;
- why it matters;
- artefacts/decisions affected;
- intended answerer;
- suggested default and consequences, when safe;
- priority;
- blocking status;
- answer and evidence when resolved.

### `ApprovalRecord`

- approval type: product, technical or later architecture;
- exact artefact version and content hash;
- approver identity;
- decision: approved, rejected or changes requested;
- rationale/comment;
- timestamp;
- superseded/revoked state.

### `ProjectActivityEvent`

- immutable event id;
- project id;
- actor/role identity;
- event type;
- related artefact refs;
- user-visible summary;
- evidence references;
- timestamp.

The exact Python class names may differ, but equivalent authority, immutability and traceability must exist.

## Canonical specification structure

The specification model must support at least:

- problem statement and intended outcomes;
- scope and explicit non-goals;
- actors and permissions;
- user journeys, alternate flows and failure flows;
- functional requirements;
- quality attributes and non-functional requirements;
- data inputs, outputs, ownership, sensitivity and retention;
- integrations and external dependencies;
- deployment, budget, technology and organisational constraints supplied by the human;
- accessibility, privacy and security expectations;
- acceptance criteria;
- assumptions;
- decisions;
- open questions;
- approval history.

A rendered Markdown document may be generated for humans and later model context, but it is a view over structured records. ATHBA must not make a single free-form HTML or Markdown blob the only authoritative representation.

## Question-generation contract

The Technical Specification Builder should produce small question batches, normally no more than eight at once.

Each question packet contains:

```text
question_ref
question
plain_language_explanation
why_it_matters
affected_requirement_or_decision_refs
blocking
intended_answerer
suggested_default (optional)
default_consequences (optional)
```

Questions must be prioritised by decision impact rather than generated as an exhaustive generic checklist.

A question should not ask a nontechnical user to choose an implementation technology unless that choice is genuinely a user-owned constraint. For example, ask how quickly a notification must arrive and what happens if delivery fails; do not ask the user to choose a message broker.

The Project Liaison presents the batch conversationally and records answers without paraphrasing away material qualifiers.

## Change-set contract

An LLM response never directly mutates project state. It proposes a validated `SpecificationChangeSet` containing operations such as:

```text
add_requirement
revise_requirement
retire_requirement
add_acceptance_criterion
record_decision
record_assumption
open_question
answer_question
propose_status_transition
```

Application services validate:

- referenced records exist;
- stable identifiers are not reused;
- approved versions are not mutated;
- contradictory operations are rejected;
- source evidence is present for material changes;
- only allowed lifecycle transitions occur;
- a role is authorised for the requested operation.

A successful change set produces a new audit event and, where appropriate, a new draft specification version.

## Project-intake state machine

```text
PROJECT_CREATED
  -> IDEA_CAPTURE
  -> SPECIFICATION_ELICITING
  -> SPECIFICATION_REVIEW_READY
  -> PRODUCT_APPROVAL_PENDING
  -> TECHNICAL_APPROVAL_PENDING
  -> ARCHITECTURE_READY
```

Permitted side states include:

```text
BLOCKED_QUESTION
CHANGES_REQUESTED
PAUSED_BY_HUMAN
SUPERSEDED
WITHDRAWN
```

Rules:

- a specification cannot become review-ready while deterministic schema validation fails;
- blocking open questions prevent approval submission;
- rejected approval returns the project to elicitation with an explicit change request;
- product approval cannot substitute for technical approval;
- technical approval cannot alter product meaning;
- any material change after approval creates a new version and invalidates only approvals that no longer match its content hash;
- architecture receives one exact `ARCHITECTURE_READY` version.

## Product and technical approval

Product approval answers:

> Does this version accurately describe what should be built, what success looks like and what is deliberately outside scope?

Technical approval answers:

> Are the supplied constraints, quality requirements, data/integration facts and unresolved risks sufficiently clear to begin architecture?

For a nontechnical project owner, ATHBA generates a plain-language approval view containing behaviours, examples, limitations and important assumptions. The technical approver receives the complete technical view and traceability.

Email may notify an approver, but approval must be recorded inside ATHBA against the exact specification version and hash. A reply to an uncorrelated email is not sufficient authority.

## Context and memory policy

The local model receives a purpose-built context packet, not the entire project conversation.

The packet should include:

- current project state;
- relevant current specification records;
- unresolved questions and recent answers;
- relevant decisions/assumptions;
- the last small window of conversation required for conversational continuity;
- explicit role instructions and output schema.

Old superseded requirements and abandoned ideas may be retrieved when needed for explanation but must be clearly marked as non-current.

The context builder is deterministic application code. It records which artefact versions were supplied to each model invocation.

## Application-service boundary

The new front-facing workflow should expose use cases rather than allow endpoints/templates to manipulate repositories directly. Expected application services include equivalents of:

- create/open project;
- submit project message;
- retrieve project snapshot;
- propose/apply specification change set;
- generate next clarification batch;
- answer clarification question;
- create review version;
- request approval;
- record approval decision;
- transition approved specification to architecture-ready;
- retrieve project activity.

The later frontend PR consumes these services. The services must be testable without a browser, MongoDB process or live model.

## Local reasoning gateway

The roles should use a local reasoning interface distinct from the bounded cloud design gateway.

The request must be capability-oriented and carry no physical placement selection. Rack AI or the local-model service determines the model/worker placement.

Tests use a scripted fake. Optional live proofs may invoke the real rack-hosted model but must not be required in CI.

Cloud fallback is forbidden. A local endpoint failure results in a visible service/blocker state and preserves the user's message for safe retry.

## Persistence and recovery

All lifecycle transitions and accepted change sets must be durable before the user is told they succeeded.

On restart, ATHBA reconstructs the project from persisted artefacts and events. It must not ask a model to infer current state from a transcript.

Idempotency keys are required for message submissions, change-set application and approval decisions so browser retries do not duplicate requirements or approvals.

## Handoff to the architecture layer

The handoff contains:

- exact approved `SpecificationVersion` id and hash;
- structured requirement, decision, assumption and question records;
- source manifest;
- product and technical approval records;
- non-blocking unresolved risks explicitly retained;
- requested architecture action identity.

The front-facing agents do not choose the architecture model and do not start a paid call. They create an `ArchitectureReadyRequest`; the bounded design service performs policy and human-authorisation checks.

## Implementation sequence

1. Introduce the new typed artefacts and repository contracts alongside legacy persistence.
2. Implement lifecycle and change-set validation in pure domain/application code.
3. Add deterministic fake local reasoning gateway and context builder.
4. Implement the Technical Specification Builder workflow against structured outputs.
5. Implement the Project Liaison workflow as a coordinator over project services.
6. Add product/technical approval workflows and immutable audit events.
7. Add read APIs required by the future workspace UI.
8. Run an opt-in live local-model proof on a disposable sample project.
9. Migrate or adapt useful legacy PM/spec behaviour; remove direct mutation paths only after parity is proven.

## Required tests

The implementation PR must prove at least:

- PM output cannot directly mutate a specification;
- the Specification Builder can only apply schema-valid, authorised change sets;
- stable refs and source evidence survive revisions;
- approved versions are immutable;
- material changes invalidate mismatched approvals;
- blocking questions prevent architecture-ready transition;
- product and technical approval remain independent;
- nontechnical approval rendering and technical rendering share the same underlying version/hash;
- restart resumes from persisted state rather than reconstructed chat meaning;
- duplicate message/change/approval submissions are idempotent;
- local model failure cannot route to cloud;
- no GPU/model/worker selector is emitted by ATHBA;
- one exact approved version is handed to the architecture layer;
- existing PR11–PR23 tests remain green after the eventual implementation is rebased onto the accepted behavioural stack.

## Live proof target

Use a disposable sample application concept and demonstrate:

1. project creation through the Project Liaison;
2. several rounds of structured specification elicitation;
3. contradiction detection and recorded resolution;
4. generated acceptance criteria and non-goals;
5. plain-language product review;
6. product approval;
7. separate technical review and approval;
8. a restart between sessions with no state loss;
9. a final immutable `ARCHITECTURE_READY` specification packet;
10. zero cloud calls.

## Non-goals

This PR does not implement:

- the final browser experience or visual redesign;
- OpenRouter or DeepSeek integration;
- principal architecture generation;
- delivery decomposition;
- Rack AI worker selection;
- behavioural TDD execution;
- email delivery implementation;
- organisation-wide identity/permissions beyond the minimum approver abstraction;
- migration to a particular TypeScript framework.

## Definition of done

The future implementation is complete when a human can collaboratively turn an idea into one exact, versioned and separately approved specification through the local Project Liaison and Technical Specification Builder; every material fact is traceable and recoverable; no agent owns hidden state or authority; and the architecture layer receives a deterministic `ARCHITECTURE_READY` handoff without any cloud expenditure.