# PR23 Development Process and Preferred Routing Catalogue

## Status

Documentation-only process catalogue for the PR23 strict-TDD path.

This document describes ATHBA's software-development stages and how ATHBA maps each model-executed stage to the generic AI execution contract. The internal stage names in this document do **not** cross into Rack AI.

The separate connector contract is `docs/pr23_generic_rack_ai_connector_contract.md`.

## Reading the catalogue

Each stage has five distinct attributes:

1. **ATHBA stage** — software-development meaning owned by ATHBA.
2. **Execution surface** — deterministic ATHBA code, structured model response, or bounded workspace change.
3. **Generic model capabilities** — only `reasoning`, `coding`, `visual`, and `audio` cross the connector.
4. **Generic scheduling parameters** — complexity, large-context flag, and priority.
5. **Current deployment result** — the worker Rack AI is expected to select from its generic registry; this is evidence/configuration, not an ATHBA worker ID request.

## Priority policy

ATHBA sets priority only after it has decided that work is semantically ready.

```text
low
  background, optional, or non-blocking work

medium
  normal ready work

high
  work currently blocking an approved critical path

paramount
  rare operator- or safety-authorized work that must outrank ordinary queues
```

Capability, priority, and readiness are orthogonal:

- a high-priority job may require only `coding`;
- a low-priority job may require `reasoning`;
- a job requiring `reasoning` is not submitted while semantically blocked;
- priority never upgrades a model capability requirement.

## Major process catalogue

| ATHBA stage | Execution surface | Generic capabilities sent | Complexity | Large context | Typical priority | Current expected Rack AI result | Mutation rights |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Behavior planning | structured response | `reasoning` | medium or large from input size | true only when source context requires it | high while blocking decomposition | reasoning-capable worker, currently primary | no repository mutation |
| Independent Gatekeeper atomization | structured response | `reasoning` | medium or large | true only for large source packet | high | reasoning-capable worker, currently primary | no repository mutation |
| Complete scenario authoring | workspace change | `reasoning`, `coding` | medium | normally false; set from measured context need | high | reasoning-plus-coding worker, currently primary | allowed test path only; scenario remains planning material |
| Scenario structural validation | deterministic ATHBA adapter | none | n/a | n/a | n/a | no Rack AI job | no mutation beyond deterministic candidate handling |
| Scenario intent review | structured response | `reasoning` | medium | normally false | high | reasoning-capable worker, currently primary | no repository mutation |
| Scenario repair | workspace change | `reasoning`, `coding` | medium | inherited from scenario context | high | reasoning-plus-coding worker, currently primary | allowed test path only; repairs exact prior candidate |
| Frontier decomposition | deterministic ATHBA adapter | none | n/a | n/a | n/a | no Rack AI job | materialises canonical test frontier deterministically |
| RED structural and boundary validation | deterministic ATHBA execution | none | n/a | n/a | n/a | no model job | no production mutation |
| Active-frontier implementation, tier 1 | workspace change | `coding` | small | false | high when on active critical path, otherwise medium | least-scarce coding worker, currently local-coder | allowed production paths only; test immutable |
| Mechanical frontier repair, tier 1 | workspace change | `coding` | small | false | high | coding worker, currently local-coder | repair current production candidate only |
| Active-frontier implementation, tier 2 | workspace change | `reasoning`, `coding` | medium | false unless evidence requires it | high | reasoning-plus-coding worker, currently primary | same immutable frontier and allowed paths |
| Focused GREEN execution | deterministic ATHBA command | none | n/a | n/a | n/a | no model job | no model mutation |
| Accumulated regression execution | deterministic ATHBA command | none | n/a | n/a | n/a | no model job | no model mutation |
| Narrow regression repair, tier 1 | workspace change | `coding` | medium | false | high | coding worker when qualified for medium bounded repair | production paths in bounded conflict set |
| Regression repair, tier 2 | workspace change | `reasoning`, `coding` | medium | false unless evidence requires it | high | reasoning-plus-coding worker | same bounded conflict set |
| Canonical revision promotion | deterministic Git/CAS service | none | n/a | n/a | n/a | no model job | exact accepted revision only |
| Senior behavior review | structured response | `reasoning` | medium | true only when accumulated context requires it | high | reasoning-capable worker, currently primary | no direct repository mutation |
| Semantic behavior repair | workspace change | `reasoning`, `coding` | medium or large | derived from repair context | high | reasoning-plus-coding worker, currently primary | production paths only; accepted tests immutable |
| Final Gatekeeper reconciliation | structured response plus deterministic evidence catalogue | `reasoning` | large | usually true for full component evidence | high | reasoning-capable large-context worker | no repository mutation |
| Post-behavior engineering refactoring | future PR21 process | not approved here | not approved here | not approved here | later | deferred | behavior frozen under accepted tests |

## Current worker visibility

The catalogue names the current expected worker only so the routing can be tested. ATHBA runtime code must not request these IDs.

Current generic registry expectation:

```text
local-coder
  capabilities: coding
  qualified envelope: small and selected medium bounded coding work
  context class: not large

local-primary
  capabilities: reasoning, coding
  qualified envelope: medium/large reasoning and coding work
  context class: large
```

If a future Rack AI backend maps the same generic request to another worker, ATHBA remains unchanged.

## Process details

### 1. Behavior planning

Input:

- component requirement;
- authoritative project context;
- current contract state.

Output:

- Behavior Contract or bounded planning result.

Generic profile:

```text
capabilities: [reasoning]
complexity: medium or large
requires_large_context: derived from actual source size
priority: high while blocking development
execution_form: structured_response
```

Failure ownership:

- malformed model response: reasoning protocol failure;
- ambiguous source requirement: ATHBA ambiguity route;
- executor/service unavailable: generic external blocker.

### 2. Independent Gatekeeper atomization

The Gatekeeper receives the source requirement independently of the Behavior Planner.

Generic profile:

```text
capabilities: [reasoning]
complexity: medium or large
priority: high
execution_form: structured_response
```

It never receives implementation or test-design authority.

### 3. Complete scenario authoring

The scenario is a complete semantic test-design artifact. It is not the immediate executable RED.

Generic profile:

```text
capabilities: [reasoning, coding]
complexity: medium
requires_large_context: normally false
priority: high
execution_form: workspace_change
```

Current expected result:

- coding-only worker ineligible;
- reasoning-plus-coding worker selected.

Attempt policy:

- maximum four actual submissions in the scenario-authoring tier;
- first attempt is fresh;
- later attempts repair the prior candidate when lineage exists;
- no-candidate result uses fresh-retry semantics;
- infrastructure failures do not consume the model budget;
- attempt five is impossible.

Mutation policy:

- only declared test path may change;
- scenario source remains planning material until approved;
- no candidate is trusted because of worker identity.

### 4. Structural validation and intent review

Structural validation is deterministic and remains in ATHBA.

If structurally accepted, intent review uses:

```text
capabilities: [reasoning]
complexity: medium
priority: high
execution_form: structured_response
```

Intent review is a separate stateless request. The same current model may be selected, but authoring and review prompts/evidence remain independent.

### 5. Scenario repair

ATHBA retains the software meaning `scenario_repair`. The connector emits the same generic profile as scenario authoring:

```text
capabilities: [reasoning, coding]
complexity: medium
priority: high
execution_form: workspace_change
```

The repair request includes exact prior source, ref/SHA, diagnostics, and semantic feedback. Rack AI does not know that this is a repair; it receives a generic workspace job.

### 6. Deterministic frontier decomposition

No model job occurs.

ATHBA's language adapter converts one approved canonical scenario into ordered, syntactically complete frontiers. Examples:

- Python blocks retain valid indentation and complete `with`/control-flow bodies;
- C# frontiers retain balanced braces and required terminators;
- VBA frontiers retain complete `If ... End If`, `For ... Next`, and procedure envelopes.

The same canonical test evolves through revision history. The adapter, not a model, creates the frontiers.

### 7. Active-frontier implementation

Tier 1 generic profile:

```text
capabilities: [coding]
complexity: small
requires_large_context: false
priority: high on the active project critical path
execution_form: workspace_change
```

The Developer receives:

- the active frontier only;
- immutable test source;
- allowed production paths;
- the exact request to make the frontier pass;
- no later fragments.

Current generic selection should prefer the coding-only worker because it is the least-scarce sufficient model profile.

### 8. Frontier escalation

After four genuine Tier-1 model failures, ATHBA changes only the generic execution profile while preserving the software work:

```text
same work_id
new submission_id
capabilities: [reasoning, coding]
complexity: medium
priority: high
execution_form: workspace_change
```

The same frontier, base SHA, allowed paths, accepted tests, and candidate history remain authoritative.

Rack AI sees no TDD escalation flag. The stronger capability request makes the coding-only worker ineligible.

### 9. GREEN, regression, and promotion

These are deterministic ATHBA operations:

```text
focused GREEN
  -> accumulated regression
  -> compare-and-swap canonical promotion
```

No reasoning call is permitted during deterministic regression.

### 10. Regression repair

A bounded, mechanically understood conflict set may first use:

```text
capabilities: [coding]
complexity: medium
priority: high
```

If ATHBA's tier policy proves the narrow route exhausted, it resubmits the same immutable repair work using:

```text
capabilities: [reasoning, coding]
complexity: medium
priority: high
```

The regression executor itself remains deterministic.

### 11. Senior behavior review

Generic profile:

```text
capabilities: [reasoning]
complexity: medium
requires_large_context: derived from accumulated evidence size
priority: high
execution_form: structured_response
```

The reviewer judges complete behavior, not every micro-frontier.

### 12. Semantic behavior repair

Generic profile:

```text
capabilities: [reasoning, coding]
complexity: medium or large
priority: high
execution_form: workspace_change
```

This route is distinct from narrow mechanical implementation.

### 13. Final reconciliation

ATHBA builds the deterministic accepted-test evidence catalogue. A reasoning job then evaluates the full checklist when semantic judgment is required:

```text
capabilities: [reasoning]
complexity: large
requires_large_context: true in the normal full-component case
priority: high
execution_form: structured_response
```

## What goes into ATHBA's internal ready collection

A work item enters `ready` only when:

- all ATHBA-owned dependencies are satisfied;
- the relevant prior frontier/review/promotion is complete;
- the trusted base is current;
- the project mutation lane permits dispatch;
- retry/tier bounds permit another submission;
- no external blocker is active.

Its internal record may include:

- ATHBA stage;
- behavior and frontier references;
- dependency state;
- required generic execution profile;
- critical-path priority;
- mutation class;
- attempt/tier state;
- trusted base and acceptance contract.

Only the generic execution profile and opaque execution data are passed through the connector.

## Dispatch policy

ATHBA does not share its ready collection with Rack AI.

The dispatcher:

1. scans ready, undispatched ATHBA work;
2. applies project mutation and idempotency rules;
3. maps the stage to a generic execution profile;
4. submits each dispatchable job once;
5. persists the submission acknowledgement;
6. waits for correlated terminal results;
7. interprets them and unlocks further internal work.

Rack AI does not receive ATHBA dependency edges or decide which behavior should run next.

## Routing proof order

Before any concurrency test:

1. deterministic profile-mapping tests;
2. generic Rack AI selector tests with fake registry;
3. sequential Rack AI qualification for `[reasoning, coding]`, `[coding]`, and stronger fallback profiles;
4. selection-decision/execution-provenance equality;
5. sequential ATHBA tiny feature;
6. process restart and persisted tier proof;
7. ReservationBook proof;
8. only then multi-worker concurrency and idle-resource optimization.

## Frozen boundaries

- No test-grammar loosening.
- No tool additions caused by model output.
- No software stage sent to Rack AI.
- No Rack AI dependency scheduling.
- No fifth model submission in a tier.
- No primary-to-coder bounce after escalation.
- No concurrent routing acceptance gate before the sequential route works.
