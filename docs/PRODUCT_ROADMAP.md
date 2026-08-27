# ATHBA Product Roadmap After Tiny Ticket

This roadmap is the durable home for product capabilities deliberately deferred while PR11-PR13 prove the ATHBA -> Rack AI development path.

## Product north star

ATHBA should feel like a collaborative AI software-development team, not a prompt-to-code batch utility. The human works primarily with a Project Manager through project chat and an editable live specification. ATHBA uses strong reasoning where planning quality has the greatest leverage, decomposes work aggressively enough that small local implementation models can succeed, and delegates bounded physical execution to Rack AI.

## Cloud planning and architecture

OpenRouter is the planned default production gateway for cloud reasoning. ATHBA should use a provider-neutral `ReasoningGateway` so model/provider changes do not contaminate domain logic.

Cloud-eligible responsibilities include specification synthesis, architecture, repository analysis, ticket/work-unit decomposition, dependency analysis, TDD/acceptance design, architecture review and difficult semantic replanning.

Policy should be configurable by project/work type and eventually cost/latency aware. Cloud planning must never select Rack AI's local GPU/model/worker directly.

## Conversational project experience

The default human-facing agent is the PM. A user should be able to open a project and collaboratively:

- describe/refine the desired product;
- inspect and edit the live specification;
- discuss architecture and trade-offs;
- approve important decisions;
- ask what is happening and why;
- see blockers/evidence/progress;
- change requirements and trigger controlled replanning.

Specialist agents can collaborate internally. Their activity should be visible through project history/dashboard and may optionally become directly addressable later, but normal UX should not require the user to route every message to the correct specialist.

## Planning and decomposition

Build a structured architecture/decomposition service that produces human stories plus a dependency DAG of deliberately tiny machine work units. Measure work-unit size against success and adapt decomposition based on evidence rather than fixed prompt rules.

## TDD engine

Evolve from fixture-based Tiny Ticket proving to an explicit RED/GREEN/refactor engine:

1. design one observable failing contract;
2. persist/verify the RED state;
3. request the smallest implementation unit;
4. require independent GREEN evidence from Rack AI;
5. repeat;
6. run story-level regression/refactor gates before completion.

Non-test work needs equivalent machine-verifiable acceptance contracts.

## Semantic replanning

Rejected execution should not simply mean 'use a bigger model'. ATHBA should classify the development-domain failure and decide among retrying unchanged, clarifying the objective, splitting the unit, expanding context requirements, changing dependencies, revising architecture or escalating planning reasoning through the cloud gateway.

## Development memory and repository intelligence

Persist architecture decisions, specification rationale, code maps, component ownership, conventions, prior work-unit attempts, accepted evidence and repeated failure patterns. Retrieval should provide planning agents with relevant project/repository history without dumping entire transcripts into prompts.

## Human-level tickets versus machine work units

Keep Kanban readable. Stories/tickets remain the project-management layer. Work-unit execution lives beneath each story with drill-down for evidence, attempts and dependency state.

## Parallelism

Once the sequential path is reliable, ATHBA should expose all dependency-ready work. Rack AI remains responsible for deciding how much can run concurrently and where it runs physically.

## Integration and release workflow

Add story/feature integration review, accepted-revision promotion, regression gates, remote Git push/PR workflows and explicit human approval policies where appropriate.

## Recovery and autonomy

Make submission idempotent and state crash-safe. ATHBA must resume a long build from persisted project/work-unit/execution state without reconstructing intent from chat history.

## Evaluation

Track at least:

- first-pass acceptance rate;
- attempts per accepted unit;
- split/replan rate;
- work-unit size versus success;
- time-to-green;
- failure classifications;
- planning-provider usage/cost/latency;
- Rack AI placement returned for successful/failed units;
- story completion and regression outcomes.

Use this evidence to improve decomposition and reasoning policy. Do not hard-code hardware assumptions back into ATHBA.

## Suggested implementation sequence

1. Production OpenRouter reasoning adapter and planning policy.
2. PM project-chat/live-spec workflow modernization.
3. Structured architecture + story/work-unit decomposition.
4. Persisted work-unit DAG and execution attempts.
5. RED/GREEN/refactor TDD engine.
6. Semantic failure classifier and replanner.
7. Project/repository memory and code intelligence.
8. Ready-work pool and safe concurrency.
9. Story integration/review and remote Git workflow.
10. Recovery/idempotency and long-running autonomous campaigns.
11. Metrics/evaluation-driven adaptive decomposition and cloud reasoning policy.

This list should be split into implementation PRs only when each slice is ready to be built; this document remains the durable source so deferred product intent is not lost.
