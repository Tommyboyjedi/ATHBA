# ATHBA + Rack AI Architecture

## Decision

ATHBA is the software-development product and development-domain control plane. Rack AI is the rack-wide execution/resource control plane.

ATHBA must be able to turn a user-approved product specification into deliberately small, dependency-aware development work that can be executed by bounded local workers. The small-work-unit/TDD strategy is intentional: it lets comparatively small local models contribute useful implementation work in aggregate. The consequence is that planning, architectural decomposition, acceptance design and replanning become more important, not less.

## Ownership

### ATHBA owns
- human-facing product development;
- project specification and architecture;
- human-level stories/tickets and Kanban state;
- decomposition into small dependency-aware development work units;
- TDD strategy and machine-verifiable acceptance requirements;
- work-unit readiness and project progression;
- semantic response to failures: clarify, split, reorder, redesign or escalate reasoning;
- project history, rationale and development memory.

### Rack AI owns
- rack-wide resource arbitration;
- GPU, model and worker selection;
- model/service lifecycle and leases;
- JCode-backed bounded execution;
- isolated worktrees, allowed-path enforcement and timeouts;
- deterministic acceptance execution and evidence capture;
- fail-closed execution policy.

ATHBA may describe complexity, capability and context needs. It must not name or select a physical GPU, local model or Rack AI worker.

## Human interaction

The end product remains collaborative rather than a batch-only code generator.

The primary interaction surface is a project chat with the Project Manager (PM). The PM is the human-facing conversational coordinator: it helps the user shape the product, edits/refines the live specification, explains proposed changes, requests approvals and reports progress/blockers.

Other specialist agents may contribute internally and their reasoning/results may be surfaced through the PM or read-only project activity views. Direct human chat with every specialist is a future UX choice, not an MVP requirement. The default architecture should avoid forcing the user to decide which agent to address for ordinary product development.

The Tiny Ticket vertical slice does not require the complete chat UX, but the PM/chat boundary is a durable product requirement and must not be designed out of the backend.

## Cloud reasoning gateway

Implementation execution should prefer the local Rack AI path, but high-value planning and architectural reasoning may require a substantially stronger model than the currently available local hardware can provide.

OpenRouter is the default planned cloud reasoning gateway for ATHBA. ATHBA should depend on a provider-neutral reasoning interface, with OpenRouter as the first production adapter rather than embedding a particular upstream model throughout the domain.

Expected cloud-eligible work includes specification synthesis, architecture design/review, decomposition, dependency analysis, acceptance/TDD strategy, difficult semantic replanning and high-context repository analysis.

Cloud use is a development-domain policy decision. It is not a Rack AI worker-selection mechanism. A cloud planner may say that a unit is complex or needs large context; ATHBA still submits capability/complexity requirements to Rack AI without choosing Rack AI's hardware/model.

For the initial Tiny Ticket MVP, the cloud gateway may be mocked or bypassed where deterministic fixtures are sufficient. The interface and architectural intent should nevertheless be preserved from the foundation PR onward.

## Ticket versus work unit

A Kanban ticket is a human/project-management concept. A development work unit is a machine-execution concept.

A single story/ticket may decompose into many deliberately tiny work units. Tiny execution units must not flood the human Kanban board.

```text
Project
  -> Story / Ticket
       -> Work Unit A
       -> Work Unit B
       -> Work Unit C
```

Each work unit should carry only the development information needed to execute and verify one bounded change: objective, allowed paths, deterministic acceptance, dependencies/readiness, capability/complexity/context requirements and bounded limits.

Execution attempts are stored separately from the work-unit definition. ATHBA may record the worker/placement chosen by Rack AI as evidence, but those values are observations only and can never be request inputs.

## TDD

TDD is an ATHBA development strategy, not a Rack AI primitive.

For suitable code work, ATHBA should prefer a narrow RED/GREEN loop: establish one failing test or observable contract; submit the smallest bounded implementation objective; have Rack AI execute deterministic acceptance independently; mark the unit complete only from accepted evidence; unlock dependent work and repeat.

Non-test work may use another machine-verifiable acceptance contract.

## Execution seam

ATHBA domain/application code talks to a `WorkUnitExecutionGateway` abstraction. The first real adapter may invoke Rack AI's `rack-ai/work-unit/v1` CLI with `--emit-json`. Future HTTP/socket transports may replace that adapter without changing the development domain.

## Progression rule

A dependency chain must execute from accepted repository state, not repeatedly from the original base revision.

For sequential work A -> B, the accepted revision produced by A becomes the starting revision for B. Rack AI should expose/promote accepted execution state safely; ATHBA should not manipulate retained Rack AI worktrees as an integration shortcut.

## Delivery sequence

### PR11 — Foundation reset
- establish this ownership boundary;
- introduce provider-neutral reasoning and work-unit execution ports;
- establish a truthful automated test/compile gate;
- repair domain/repository/test drift before Rack AI integration;
- retain existing PM/spec/Kanban behaviour.

### PR12 — Work-unit domain + Rack AI adapter
- add `DevelopmentWorkUnit` and `ExecutionAttempt` domain records;
- dependency/readiness evaluation;
- strict `rack-ai/work-unit/v1` serializer/result parser;
- fake execution gateway for tests;
- first real Rack AI CLI adapter;
- prohibit GPU/model/worker identifiers from ATHBA requests.

### PR13 — Tiny Ticket vertical slice
- add a small development coordinator;
- execute ready units through Rack AI;
- consume structured acceptance/evidence;
- progress dependencies only after acceptance;
- bounded retry/replan hooks;
- prove a real Tiny Ticket application through ATHBA -> Rack AI -> JCode.

### Later product work
- OpenRouter production adapter and configurable cloud reasoning policy;
- full PM conversational project UX and live specification collaboration;
- richer architecture/decomposition/replanning;
- work-unit drill-down beneath human Kanban tickets;
- development memory and repository intelligence;
- parallel ready-work pools while Rack AI owns physical scheduling;
- story/feature integration review and remote Git/PR workflows;
- evaluation of work-unit size, first-pass success, retries, splits and time-to-green.

## Design principle

Use expensive/strong reasoning where it has the highest leverage: deciding what should be built, how it should be divided, and how success is proved. Use deliberately small bounded work units to make local implementation models productive in aggregate. Keep physical execution/resource policy below ATHBA in Rack AI.
