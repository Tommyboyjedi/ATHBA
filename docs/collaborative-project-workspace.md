# Collaborative Project Workspace and Frontend Modernisation

## Status

Documentation-only product and implementation contract.

This PR depends on the local Project Liaison and Technical Specification Builder contract in PR24. It defines the browser experience and API boundary only. It does not implement agent reasoning, cloud architecture, Rack AI execution or a final visual design.

## Goal

Replace the current collection of Django pages, partials and agent-specific interactions with one coherent project workspace in which a human can:

- discuss the product with the Project Liaison;
- inspect and edit the live canonical specification;
- answer prioritised clarification questions;
- review decisions, assumptions and non-goals;
- grant or reject product, technical and later architecture approvals;
- see architecture and delivery-compilation status;
- monitor local execution progress and evidence;
- understand and act on human-intervention requests.

The workspace should look and behave like a modern product, but visual quality must not come at the cost of moving authority, secrets or workflow logic into the browser.

## Core decisions

1. Django remains the authoritative backend and application-service host during the frontend migration.
2. The frontend consumes explicit versioned APIs and event streams rather than reaching into repositories or agent objects.
3. TypeScript is the target language for the richer browser client. The framework choice is deferred to a focused ADR and proof, rather than silently committing ATHBA to React, Angular or another framework in this planning PR.
4. The migration is incremental. Existing server-rendered routes remain available until equivalent workspace behaviour is proven.
5. The Project Liaison is the default conversational surface. Users are not required to pick an internal specialist agent for ordinary project work.
6. The browser never stores a cloud-provider key, local-model credential or Rack AI credential.
7. Approval actions are explicit, attributable and tied to exact artefact versions and hashes.
8. The user interface reflects persisted server state; it never treats locally rendered optimism as proof that an authoritative transition succeeded.

## Product experience

### Project workspace shell

The default project route should provide a durable shell with the following regions.

#### Project header

- project name and lifecycle state;
- active specification, architecture and campaign versions;
- clear local/cloud phase indicator;
- current blocker or next required human action;
- project-level actions such as pause, archive and settings;
- visible but unobtrusive cost ledger for the design phase.

#### Project Liaison conversation

- continuous project conversation;
- streaming responses when supported;
- source-aware cards for questions, decisions, approvals and blockers;
- ability to open the related specification or evidence item directly;
- queued/submitted/accepted/failed message state;
- safe replay of a user message after transient local-model failure without duplication;
- no requirement for the human to address `@Spec`, `@Architect` or another internal role.

#### Canonical specification panel

- plain-language and technical views over the same specification version;
- structured sections and stable requirement identifiers;
- visible provenance and change history;
- proposed versus accepted changes;
- inline comments or human edits where permitted;
- contradiction, missing-information and validation indicators;
- version comparison and approval state;
- explicit non-goals and assumptions, not only positive requirements.

#### Questions and decisions panel

- prioritised clarification questions;
- reason each question matters;
- affected requirement/decision references;
- blocking status;
- proposed defaults and consequences;
- answer, defer or route to another approver;
- decision log with alternatives and rationale.

#### Approval centre

- product approval packet;
- technical approval packet;
- later architecture approval packet;
- exact version/hash being approved;
- changes since the previous reviewed version;
- approve, reject or request changes;
- audit identity and timestamp;
- no generic confirmation button that can accidentally approve a different artefact.

#### Architecture and delivery panel

Before campaign sealing, show:

- requirements-review rounds and their status;
- architecture dossier readiness;
- estimated and actual external-model spend;
- explicit authorisation state for any principal-architect call;
- architecture validation findings;
- decomposition progress and unresolved blockers;
- campaign-seal readiness.

The UI may present summaries, but it must make the underlying artefacts available for direct inspection.

#### Local execution panel

After campaign sealing, show:

- a clear `LOCAL_ONLY` state;
- human stories and their underlying behavioural work;
- dependency/readiness status;
- current local work and accepted revisions;
- attempts, tests, reviews and evidence;
- blocked branches while unrelated ready work continues;
- human-intervention packets;
- an explicit statement that the system cannot initiate a paid model from this phase.

The human Kanban must remain readable. Machine-level TDD frontiers and work units belong beneath a ticket/story drill-down rather than becoming hundreds of top-level cards.

## Information architecture

A suggested route model is:

```text
/projects
/projects/{project_id}
/projects/{project_id}/specification
/projects/{project_id}/decisions
/projects/{project_id}/approvals
/projects/{project_id}/architecture
/projects/{project_id}/delivery
/projects/{project_id}/activity
/projects/{project_id}/settings
```

These may be client-side routes inside one workspace or Django routes during transition. The durable requirement is stable deep linking to an artefact or evidence item.

## Frontend architecture

### Django authority

Django remains responsible for:

- authentication and authorisation;
- project/application services;
- validation and lifecycle transitions;
- persistence;
- idempotency;
- model and Rack AI gateway orchestration;
- approval authority;
- event production;
- server-side audit history.

Templates or the TypeScript client never bypass these services.

### TypeScript client target

The target browser client should use TypeScript for:

- typed API contracts;
- workspace state and route handling;
- streaming/event reconciliation;
- accessible reusable components;
- rich specification and evidence views;
- robust client-side validation for user experience, while retaining server validation as authority.

The implementation PR must create an ADR comparing at least:

- progressive enhancement of Django/HTMX with TypeScript modules;
- a standalone or embedded TypeScript single-page workspace;
- the build/deployment complexity each adds;
- accessibility and maintainability;
- compatibility with streaming, rich editors and long-running project state;
- incremental migration and rollback.

No framework should be selected because it is fashionable or because an LLM generates it easily. The smallest architecture that delivers a polished, maintainable workspace wins.

### API contract source

The backend should expose schemas from which frontend types can be generated or verified. OpenAPI or an equivalent explicit schema is preferred over manually duplicated Python and TypeScript shapes.

A frontend build must fail when generated/checked types drift from the server contract.

### Event transport

Use an authenticated project event stream for long-running updates. Existing SSE capability may be retained if it satisfies reconnect, cursor and ordering requirements. WebSockets are not required unless bidirectional real-time behaviour genuinely needs them.

Events must include:

```text
event_id
project_id
event_type
project_sequence
occurred_at
related_artifact_refs
payload_version
user_visible_summary
```

The client persists a cursor, reconnects safely, de-duplicates events and requests a fresh project snapshot when continuity cannot be trusted.

## Backend API use cases

Exact URLs may evolve, but the UI needs versioned operations equivalent to:

### Project snapshot

```text
GET project snapshot
```

Returns the authoritative project state, active artefact versions, pending questions/approvals, architecture state, execution summary and latest event cursor.

### Conversation

```text
POST project message
GET conversation page/history
```

The message request carries an idempotency key. The response acknowledges durable receipt, not necessarily completed model processing. Subsequent events report accepted artefact proposals or failures.

### Specification

```text
GET specification version
GET specification diff
POST proposed human edit
POST apply/accept change set
POST create review version
```

Human edits become validated server-side change operations. The browser does not overwrite a canonical blob blindly.

### Questions and decisions

```text
GET open questions
POST answer question
POST defer/route question
GET decision log
POST record human decision
```

### Approvals

```text
GET approval packet
POST approval decision
```

The request includes the exact artefact version and content hash observed by the user. The server rejects stale approval attempts.

### Architecture and cloud authorisation

```text
GET architecture/design status
GET cloud cost preflight
POST authorise permitted design call
POST reject/cancel design call
GET architecture bundle/validation findings
```

There is no generic endpoint that lets the frontend submit arbitrary prompts, providers or model identifiers.

### Execution and intervention

```text
GET campaign/story/work summary
GET work/evidence detail
GET human intervention packet
POST acknowledge intervention
POST record human resolution or revised artefact reference
```

The frontend cannot request cloud escalation from a sealed campaign.

## Server state versus client state

The client may keep view preferences, unsent drafts and transient UI state. It must not become authoritative for:

- current project lifecycle;
- specification or architecture versions;
- approval status;
- campaign seal state;
- accepted repository revisions;
- execution verdicts;
- cloud budget/usage;
- blocker resolution.

Optimistic updates are acceptable only when visibly pending and reconciled against the authoritative response/event. Approval and campaign-seal transitions should normally avoid optimistic success entirely.

## Editing model

The specification editor must operate on structured sections/records rather than an unversioned rich-text document.

A polished rich editor may be used for prose fields, but it must preserve stable IDs and structured semantics. Copy/paste, Markdown import and AI-proposed changes should produce reviewable operations.

Concurrent edit handling must at least detect stale base versions. Silent last-write-wins behaviour is unacceptable for approved or review-ready specifications.

## Authentication, authorisation and approvers

The first implementation may use a modest identity model, but it must distinguish:

- project participant;
- product approver;
- technical approver;
- architecture approver, when required;
- administrator.

The browser cannot assert these roles. Django resolves them from authenticated identity and project policy.

Approval links sent by email must lead to an authenticated approval packet. A URL token alone must not become a reusable bearer authority without an explicit security decision.

## Cloud-cost presentation

The workspace should reinforce the cost policy rather than hide it.

Before a permitted cloud call, show:

- purpose;
- configured model alias and resolved provider/model;
- estimated input and maximum output tokens;
- estimated maximum charge;
- remaining project/phase budget;
- whether this consumes the one permitted principal-architect result;
- explicit authorisation action.

After completion, show actual usage and charge from the gateway ledger.

After campaign sealing, the cloud-cost section becomes read-only history and displays `EXTERNAL MODEL CALLS DISABLED FOR EXECUTION`.

## Human-intervention experience

A blocker must be actionable rather than a red error banner.

The UI should present:

- affected story/behaviour/work unit;
- last trusted revision;
- what was attempted;
- exact failure classification;
- concise local-model diagnosis;
- relevant diffs, tests, stdout/stderr and evidence links;
- dependencies and other work that can continue;
- permitted human actions;
- how to record a manual fix, clarification or architecture revision;
- confirmation that no paid call was made.

Manual use of ChatGPT, Codex, Grok or another human-controlled tool is outside ATHBA. The UI may allow the resulting patch/decision to be recorded, but it must never invoke those subscriptions automatically.

## Accessibility and responsive design

Accessibility is a product requirement, not a later styling pass.

The implementation must include:

- keyboard-complete navigation;
- visible focus;
- semantic landmarks and headings;
- screen-reader labels and live-region discipline for streaming updates;
- colour-independent status meaning;
- sufficient contrast;
- reduced-motion support;
- responsive layouts that remain usable on a laptop or tablet;
- accessible diffs, tables and evidence viewers;
- automated accessibility checks plus manual keyboard/screen-reader review of critical flows.

## Design system

Introduce a small design-token and component layer for:

- typography and spacing;
- surface/elevation hierarchy;
- status and severity semantics;
- buttons, forms, tabs and dialogs;
- artefact references;
- approval cards;
- question cards;
- timeline/events;
- code/diff/evidence viewers;
- empty, loading, degraded and disconnected states.

The design system should not become a separate product or a dependency-heavy exercise. It exists to keep the workspace coherent and polished.

## Failure and degraded states

The client must handle explicitly:

- local model unavailable;
- event stream disconnected or sequence gap;
- stale specification edit;
- stale approval packet;
- architecture call not authorised;
- architecture call transport failure with no automatic retry;
- server restart during long-running activity;
- campaign sealed while an old browser tab remains open;
- user loses permission;
- execution blocker while other branches progress.

A degraded UI must not guess success from absence of an error.

## Migration strategy

1. Inventory existing routes, templates, JavaScript, CSS, HTMX and SSE behaviour.
2. Define the project snapshot, command and event contracts in Django.
3. Add contract tests and generated/verified TypeScript types.
4. Build the workspace shell against fake fixture data.
5. Connect read-only project/specification/activity views.
6. Add conversation submission and event reconciliation.
7. Add structured specification editing and questions.
8. Add approvals with stale-version protection.
9. Add architecture and execution views.
10. Run parity tests against existing functionality.
11. switch the default project route only after critical workflows pass.
12. Remove legacy routes incrementally, retaining rollback until production confidence exists.

The first frontend implementation PR should be small enough to prove the shell, typed API and event flow rather than attempting every panel at once.

## Required tests

The implementation series must prove at least:

- the browser cannot directly mutate repository/domain state;
- generated/checked TypeScript types match server schemas;
- duplicate message submissions are idempotent;
- event reconnect de-duplicates and resumes from a cursor;
- a sequence gap forces snapshot reconciliation;
- stale specification edits are rejected visibly;
- stale approval hashes are rejected;
- approval success is not shown before server acceptance;
- no API accepts arbitrary provider/model/prompt input from the browser;
- no cloud credential appears in frontend assets or responses;
- sealed-campaign APIs expose no cloud escalation command;
- local execution evidence is drill-down data beneath human-level stories;
- keyboard and automated accessibility tests cover critical paths;
- the legacy UI remains usable until replacement parity is accepted.

## Initial live proof

Using a disposable project, demonstrate in a real browser:

1. open the project workspace;
2. send a message to the Project Liaison;
3. receive a streamed or asynchronously completed response;
4. inspect a structured specification change and its source reference;
5. answer a blocking clarification question;
6. create and compare a review version;
7. attempt and reject a stale approval;
8. successfully approve the current product version;
9. reconnect the event stream after interruption without duplicate events;
10. inspect an architecture-ready handoff;
11. inspect a fixture local-execution blocker with no cloud action available;
12. complete critical flows by keyboard.

## Non-goals

This PR does not decide or implement:

- the Project Liaison or Technical Specification Builder reasoning workflows;
- a final JavaScript framework before the ADR/proof;
- the cloud architecture pipeline;
- Rack AI scheduling or worker placement;
- the behavioural TDD engine;
- automatic email sending;
- mobile-native applications;
- public multi-tenant SaaS deployment;
- organisation-wide RBAC beyond the initial project/approver boundary.

## Definition of done

The future frontend implementation is complete when the human can carry the project from conversation through specification review, approvals, architecture visibility and local execution monitoring in one polished, accessible workspace; every command is validated by Django application services; TypeScript and backend contracts remain aligned; and neither authority nor paid-model credentials leak into the browser.