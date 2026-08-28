# PR16 — Architect decomposition and senior semantic review

## Goal

Move ATHBA one layer upward from PR15.

PR15 proved that, when ATHBA is given an ordered list of `TddBehavior` objects, it can drive a real RED -> GREEN loop through Rack AI/JCode/local models while preserving trusted repository progression.

PR16 must remove the largest manual step in that proof:

1. take a modest higher-level software requirement;
2. have ATHBA's Architect/decomposition layer produce the `TddBehavior` sequence that PR15 previously received by hand;
3. feed that generated sequence into the existing PR15 TDD loop;
4. after each GREEN result has passed Rack AI acceptance, perform an ATHBA-owned senior-engineer semantic/code-quality review;
5. advance to the next behavior only after that semantic review approves the implementation.

This PR does not attempt full application architecture, broad natural-language product planning, UI work, or the full Tiny Ticket application.

## Why this PR exists

Rack AI answers a mechanical and safety question:

> Did this bounded change remain inside authority, satisfy deterministic acceptance, and produce a trusted accepted revision?

PR15 answers the TDD sequencing question:

> Did ATHBA correctly create RED, then GREEN, and preserve revision progression?

Neither layer answers the senior-engineering question:

> Even though the tests pass, is this actually a good implementation of the intended behavior and consistent with the design we are trying to build?

The PR15 live proof produced working code but also showed examples of small-model noise and mediocre engineering quality, including unnecessary imports/comments, misleading comments, and speculative/noisy test annotations in some attempts.

That is not primarily a Rack AI acceptance defect. It is an ATHBA semantic review concern.

PR16 therefore proves the first complete local development slice with three distinct gates:

```text
higher-level requirement
        |
        v
ATHBA Architect/decomposer
        |
        v
structured TDD behavior plan
        |
        v
PR15 RED -> GREEN loop
        |
        v
Rack AI acceptance / trusted candidate revision
        |
        v
ATHBA senior semantic review
        |
    +---+---+
    |       |
 approve  repair required
    |       |
    v       v
 next      bounded repair -> Rack AI -> review again
 behavior
```

## Proof target: ReservationBook

Use a fresh disposable Python 3.14 repository. Do not reuse the PR15 TaskQueue fixture as the decomposition target.

Give ATHBA the following higher-level requirement as the Architect input. Do not pre-split it into TDD behaviors in production code or the live runner.

> Build a small in-memory `ReservationBook` for reservable resources. A resource has a unique id and a positive integer capacity. Clients can add resources, create uniquely identified reservations for a number of units on a resource, cancel reservations, and query remaining availability. Duplicate resource ids and duplicate reservation ids must be rejected. Reservations for unknown resources, cancellations of unknown reservations, invalid/non-positive quantities, and reservations that exceed remaining capacity must be rejected without corrupting state. Cancelling a reservation restores that capacity. The implementation is in-memory only, dependency-free, and should remain small, direct, readable Python rather than introducing unnecessary abstractions.

This is intentionally larger than one TaskQueue behavior but still small enough to reason about as one class/component.

The Architect must decide the actual behavior sequence, dependencies, focused test names, and RED/GREEN work-unit descriptions.

## Architect output

The decomposition layer should output a structured plan, not free-form prose.

Reuse or extend `TddBehavior` where sensible. The generated plan needs enough information for the existing TDD loop to derive Tester and Developer work units of the quality demonstrated in the successful PR15 live prompts.

At minimum each behavior should have:

- stable behavior id;
- concise human-readable objective;
- test name/node id;
- test path;
- production path;
- dependency/order information where genuinely required;
- RED objective/prompt material;
- GREEN objective/prompt material;
- deterministic RED acceptance command;
- deterministic GREEN acceptance commands;
- expected exception type/message when relevant;
- expected observable result/state when relevant.

Do not include GPU/model/worker ids.

Do not require exact wording identical to the PR15 prompts, but use the accepted PR15 prompts as empirical reference for the amount of specificity small local workers required.

## Decomposition quality rules

The Architect/decomposer must aim for behaviors that are:

- small enough for one focused test;
- externally observable;
- independently understandable;
- minimally overlapping;
- ordered only where dependency genuinely exists;
- explicit about error behavior and state preservation;
- specific enough that Tester does not need to redesign the feature;
- specific enough that Developer does not need to infer unrelated requirements;
- free from concrete implementation code unless essential to identify an API contract;
- suitable for PR15's strict test-path RED and production-path GREEN authority.

The b5 outcome from PR15 is important evidence: a later behavior was already satisfied by earlier minimal code. Some overlap is unavoidable, but the decomposition layer should actively minimize redundant behavior definitions rather than blindly producing a checklist.

## Plan validation before execution

Before starting RED/GREEN execution, validate the generated behavior plan.

Deterministic validation should cover at least:

- unique behavior ids;
- unique focused test names;
- non-empty objectives;
- valid repository-relative test/production paths;
- no self-dependencies;
- no unknown dependencies;
- acyclic dependency graph;
- required RED/GREEN commands present;
- no physical resource-selection fields;
- behavior plan covers the stated high-level requirements in a traceable way.

If coverage of the high-level requirement cannot be demonstrated, fail before implementation rather than silently dropping requirements.

## Requirement traceability

Represent enough traceability to answer:

- which high-level requirement(s) is this behavior intended to satisfy?
- which behavior/test proves it?
- which accepted/semantically-approved revision implemented it?

The proof does not need a sophisticated requirements database. A compact structured mapping is sufficient.

## Senior semantic/code review gate

After a GREEN work unit passes Rack AI acceptance, its `accepted_revision` is a trusted mechanically accepted **candidate** revision.

ATHBA must not automatically treat that candidate as semantically complete.

Run an ATHBA-owned senior-engineer review before advancing the behavior.

The reviewer should inspect, at minimum:

- behavior requirement;
- relevant generated test(s);
- candidate diff or changed production file(s);
- previously approved behavior/design context;
- Rack AI result/evidence as useful context.

The reviewer is not replacing Rack AI. It must not re-run or reinterpret path/safety authority as its main job.

## Review criteria

The senior review should judge whether the implementation:

- actually expresses the intended behavior, not merely the narrowest accidental way to satisfy the test;
- preserves previously accepted behavior;
- is simple and direct;
- avoids speculative features and abstractions;
- uses clear names;
- avoids dead/unused imports and dead code;
- avoids misleading or excessive comments/docstrings;
- avoids test-gaming or implementation tricks;
- avoids duplicated logic where an obvious simple structure exists;
- is idiomatic enough for the target language/project;
- remains consistent with the component-level design and current behavior plan;
- does not create an obvious maintainability problem that a competent senior developer would send back in review.

For example, code can pass tests and still deserve repair if it adds an unused import, misleading comment, unnecessary abstraction, inappropriate global state, or other obvious junior-developer noise.

## Structured review result

Use a small structured result such as:

- `approved`
- `repair_required`
- `replan_required`

with:

- concise rationale;
- concrete findings;
- optional bounded repair instructions;
- evidence/reference to candidate revision and behavior id.

`replan_required` is for cases where the problem is not merely code quality but the generated behavior/decomposition itself is flawed, contradictory, redundant, or insufficient.

Do not allow arbitrary unstructured reviewer prose to become orchestration state.

## Candidate revision versus semantically approved revision

Keep these concepts distinct.

Rack AI GREEN acceptance produces a trusted candidate revision.

ATHBA semantic approval determines whether that candidate is allowed to become the base for the next behavior.

If semantic review approves:

```text
last semantic base G0
 -> RED R1
 -> GREEN candidate G1
 -> review approved
 -> semantic base becomes G1
 -> next behavior starts from G1
```

If review requires repair:

```text
last semantic base G0
 -> RED R1
 -> GREEN candidate G1
 -> review repair_required
 -> bounded repair starts from G1
 -> Rack AI acceptance gives G1r
 -> semantic review runs again
 -> only approved G1r becomes the next semantic base
```

A rejected semantic review must not allow the next behavior to start.

Do not delete or pretend the Rack AI candidate revision did not exist; retain it as evidence/history.

## Repair loop

Implement the smallest bounded repair loop necessary for this proof.

When review returns `repair_required`:

- create a narrowly scoped repair work unit;
- start from the mechanically accepted candidate revision;
- production path only unless the review explicitly identifies a test/decomposition defect (which should normally become `replan_required` instead);
- preserve the same behavior's accumulated tests;
- run normal Rack AI acceptance;
- obtain a new trusted candidate revision;
- re-run semantic review;
- bound the number of semantic repair attempts (for example 2) and fail closed after the budget is exhausted.

Do not turn this into an unlimited self-editing loop.

## Reviewer/decomposer reasoning boundary

Architect decomposition and senior semantic review require judgment, so they should depend on ATHBA's provider-neutral reasoning abstractions rather than hard-coded model identities.

Prefer the existing `ReasoningGateway` seam where appropriate.

The live PR16 proof should use local reasoning on `gpurack`, not default to a cloud model.

However:

- ATHBA domain/application code must not name a GPU, worker, model id or local endpoint;
- do not silently bypass the Rack AI resource-authority boundary merely because reasoning is read-only;
- inspect the current Rack AI/ATHBA runtime and use the cleanest existing local reasoning path available;
- if a genuine missing Rack AI non-mutating reasoning-dispatch capability prevents a boundary-correct live implementation, document that concrete gap and stop rather than hard-coding `local-primary`/ports into ATHBA.

Do not use OpenRouter/cloud reasoning as the default acceptance proof for PR16.

## Prompt construction

Use the successful PR15 live Tester/Developer prompts as evidence for prompt quality.

Do not store a giant hard-coded prompt per behavior.

Build role-specific prompt templates from structured behavior fields and current progression state.

Tester prompt generation should reliably convey:

- RED role;
- exact writable test path;
- exact new test name;
- exact behavior/expected result;
- preserve existing accepted tests;
- add exactly one focused test;
- no production reasoning/changes;
- no speculative helpers/extra tests;
- repository-relative path requirements.

Developer prompt generation should reliably convey:

- GREEN role;
- exact writable production path;
- focused test name;
- full accumulated tests also run;
- preserve prior behavior;
- minimal implementation only;
- no test edits;
- no speculative abstraction/noise.

Prompt quality is part of the decomposition output contract because weak prompts materially affected the PR15 live runs.

## Live proof

Run the full local path on `gpurack` with the ReservationBook requirement.

No hand-authored TDD behavior sequence is allowed in the live proof.

The live flow must be:

```text
ReservationBook requirement
 -> ATHBA Architect/decomposer
 -> generated structured behavior plan
 -> plan validation
 -> PR15 TDD coordinator
 -> RED through Rack AI/JCode/local model
 -> GREEN through Rack AI/JCode/local model
 -> Rack AI candidate accepted revision
 -> ATHBA senior semantic review
 -> approve or bounded repair
 -> next generated behavior
 -> completed ReservationBook
```

The final repository must satisfy the original high-level ReservationBook requirement and the accumulated generated test suite.

## What to record from the live proof

Retain/report:

- exact original requirement input;
- generated behavior plan in order;
- requirement-to-behavior traceability;
- generated Tester/Developer objectives/prompts or reproducible prompt inputs;
- RED/GREEN/candidate revisions;
- semantic review decision for every GREEN candidate;
- any repair work units and repaired revisions;
- final semantically approved revision;
- final full pytest result;
- final source implementation;
- evidence packet locations;
- any redundant/already-satisfied behavior discovered;
- any decomposition defect requiring replan;
- which reasoning path/provider was used without exposing that choice as domain authority.

## Tests required

Add deterministic tests proving at least:

1. decomposition output can be parsed into valid `TddBehavior` objects;
2. malformed/missing behavior fields fail closed;
3. duplicate ids/test names fail validation;
4. invalid/cyclic dependencies fail validation;
5. requirement traceability is retained;
6. generated plan does not contain physical resource selection;
7. TDD execution uses generated behaviors, not a hidden hard-coded fallback list;
8. semantic review runs after accepted GREEN and before next behavior;
9. reviewer approval advances the semantic base;
10. `repair_required` prevents next behavior and creates a bounded repair step;
11. repaired candidate is reviewed again;
12. `replan_required` stops execution and surfaces the decomposition problem;
13. semantically rejected candidate never becomes next behavior base;
14. review/repair history persists;
15. resume does not repeat already semantically approved behavior;
16. existing PR11-PR15 tests remain green under Python 3.14.

## Non-goals

Do not add in PR16:

- full Tiny Ticket application build;
- broad multi-project planning;
- PM/UI redesign;
- rich dashboard;
- parallel DAG execution;
- generalized refactoring framework;
- automatic cloud escalation;
- OpenRouter as default reasoning path;
- Rack AI scheduling redesign;
- direct GPU/model/worker selection in ATHBA;
- a huge universal software architecture engine.

PR14 remains the broader roadmap/idea holder and should not be rewritten by this PR.

## Definition of done

PR16 is complete when:

1. ATHBA accepts the higher-level ReservationBook requirement without a hand-written behavior list;
2. local Architect/decomposition produces a valid structured TDD behavior plan;
3. the plan is validated and traceable to the input requirement;
4. generated behaviors feed the existing PR15 TDD loop;
5. every GREEN candidate passes through ATHBA senior semantic review before progression;
6. repair-required candidates can be corrected through a bounded Rack AI repair loop and re-reviewed;
7. semantically rejected/unreviewed code never advances the semantic base;
8. final ReservationBook satisfies the original requirement and all accumulated tests;
9. full ATHBA Python 3.14 suite and compile gate remain green;
10. live proof uses local rack reasoning/execution without hard-coded physical identities in ATHBA;
11. all decomposition/review/TDD evidence is durable enough to reconstruct what happened.

Report the final proof explicitly as:

`PR16_DECOMPOSITION = PASS|FAIL`

`PR16_SEMANTIC_REVIEW = PASS|FAIL`

`PR16_END_TO_END_COMPONENT = PASS|FAIL`
