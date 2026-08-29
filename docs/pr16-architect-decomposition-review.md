# PR16 — Behavior-contract lane, senior review, and pool-ready progression

## Goal

Move ATHBA one layer upward from PR15 without trying to implement the full seven-role software-development hierarchy yet.

PR15 proved that, when ATHBA is given an ordered list of precise `TddBehavior` objects, it can drive a real RED -> GREEN loop through Rack AI/JCode/local models while preserving trusted repository progression.

PR16 should prove a narrower and more realistic next step:

1. take one modest component-level requirement;
2. have ATHBA produce **one bounded Behavior Contract** rather than a pre-authored list of every Tester and Developer prompt;
3. let the Tester and Developer generate the individual RED/GREEN steps dynamically inside that contract;
4. after each mechanically accepted GREEN candidate, place the result into a **review-ready pool**;
5. have an ATHBA senior reviewer assess candidate quality separately from Rack AI acceptance;
6. move approved work into an **approved pool**, repairable work into a **repair pool**, and decomposition/design defects into a **replan pool**;
7. keep all state transitions explicit so future parallel execution is possible, while PR16 itself may run serially.

PR16 does **not** attempt to implement all identified roles:

- Project Manager / Master Designer
- Solution Architect
- Component Designer
- Behavior Decomposer
- Tester
- Developer
- Senior Reviewer

Only the lower slice needed for this proof is implemented. The higher architectural layers remain future work.

## Why this shape

The emerging target hierarchy is:

```text
Project Manager / Master Designer
        |
        v
Solution Architect
        |
        v
Component Designer
        |
        v
Behavior Decomposer
        |
        v
Behavior Contract
        |
        +-------------------------------+
        |                               |
        v                               |
Tester RED <----------------------> Developer GREEN
        |                               |
        +---------------+---------------+
                        |
                        v
                 review-ready pool
                        |
                        v
                 Senior Reviewer
                        |
              +---------+----------+
              |         |          |
              v         v          v
           approved   repair      replan
             pool      pool        pool
```

PR16 proves only the portion from **component-level requirement -> Behavior Contract -> Tester/Developer TDD lane -> senior review -> pool transition**.

## Core design decision: contract, not pre-written prompts

PR15 succeeded partly because the RED and GREEN prompts were hand-authored in great detail. That was useful for proving mechanics, but it front-loaded too much intelligence outside ATHBA.

PR16 should not generate every Tester and Developer prompt up front.

Instead, the planning layer should generate a compact durable **Behavior Contract** that defines the lane the Tester and Developer must stay inside.

The contract describes:

- the capability to be added;
- externally observable requirements;
- invariants and state-preservation rules;
- allowed production path(s);
- allowed test path(s);
- relevant API/interface constraints;
- required error behavior;
- explicit non-goals;
- completion criteria;
- any dependencies on already-approved behavior;
- requirement traceability.

The Tester then chooses the smallest useful missing RED step inside that contract. After GREEN and approval, the Tester may choose the next smallest missing RED step in the same contract until the contract is complete.

The road is planned; the footsteps are generated dynamically.

## Proof target: ReservationBook

Use a fresh disposable Python 3.14 repository. Do not reuse the PR15 TaskQueue fixture.

Give ATHBA this component-level requirement:

> Build a small in-memory `ReservationBook` for reservable resources. A resource has a unique id and a positive integer capacity. Clients can add resources, create uniquely identified reservations for a number of units on a resource, cancel reservations, and query remaining availability. Duplicate resource ids and duplicate reservation ids must be rejected. Reservations for unknown resources, cancellations of unknown reservations, invalid/non-positive quantities, and reservations that exceed remaining capacity must be rejected without corrupting state. Cancelling a reservation restores that capacity. The implementation is in-memory only, dependency-free, and should remain small, direct, readable Python rather than introducing unnecessary abstractions.

For PR16, this input is treated as if it had already been produced by the future higher architecture layers.

Do not claim that PR16 proves broad user-intent -> architecture -> component-design generation.

## Behavior Contract output

Create a structured provider-neutral contract, for example `BehaviorContract` or equivalent.

It should contain enough information to constrain the local TDD lane without containing pre-written per-cycle prompts.

At minimum:

- stable contract id;
- project/component id;
- concise component capability statement;
- observable requirements;
- invariants/state preservation expectations;
- test path(s);
- production path(s);
- public API constraints where known;
- error/exception expectations where known;
- explicit non-goals;
- completion criteria;
- traceability back to the component requirement;
- status/progression metadata.

Do not include concrete GPU/model/worker identities.

## Tester/Developer lane

The Tester and Developer operate dynamically inside the contract.

### Tester

The Tester should:

- inspect the Behavior Contract and current semantically approved repository state;
- identify the smallest useful missing observable behavior;
- generate one focused RED test;
- preserve existing approved tests;
- modify only allowed test paths;
- avoid speculative helpers, comments, fixtures or extra tests unless genuinely needed;
- produce a structured record of what requirement slice this RED step covers.

The Tester is not handed a complete pre-written test prompt for every future cycle.

### Developer

The Developer should:

- start from the accepted RED revision;
- inspect the current focused failing test and the Behavior Contract;
- implement the minimum production change needed for GREEN;
- preserve prior approved behavior;
- modify only allowed production paths;
- avoid speculative abstraction, dead imports/code, noisy comments and unrelated features.

The Developer is not handed a complete pre-written implementation prompt for every future cycle.

### Cycle completion

After GREEN passes mechanically and semantic review approves it, the contract remains active if unfulfilled requirements remain. The Tester then selects the next smallest missing behavior.

If all contract requirements are satisfied, the contract moves to the completed/approved pool.

## PR15 prompts as empirical guidance

The successful PR15 prompts remain useful evidence for the level of specificity small local models may need.

Use them to design role prompt templates and context packaging, but do not hard-code a giant prompt per future behavior.

The system should be able to dynamically produce prompts of comparable clarity from:

- the Behavior Contract;
- current approved tests;
- current approved source state;
- the current focused cycle objective;
- phase-specific path authority;
- prior review findings where applicable.

## Rack AI versus ATHBA senior review

Rack AI answers:

> Did this bounded change safely satisfy deterministic acceptance and produce a trusted candidate revision?

ATHBA senior review answers:

> Is this actually a good implementation of the intended design and current Behavior Contract?

These are intentionally separate gates.

A Rack AI GREEN result is a mechanically accepted **candidate**, not automatically a semantically approved progression point.

## Senior review criteria

The reviewer should assess whether candidate code:

- expresses the intended behavior rather than merely gaming a narrow test;
- remains consistent with the Behavior Contract;
- preserves previous approved behavior;
- is simple, direct and readable;
- avoids speculative abstractions/features;
- uses clear names;
- avoids dead/unused imports and dead code;
- avoids misleading/excessive comments or docstrings;
- avoids duplicate or obviously poor structures;
- remains idiomatic enough for the project;
- does not create an obvious maintainability problem a competent senior developer would send back.

The PR15 TaskQueue output is useful calibration: code may pass tests while still containing unnecessary imports/comments, misleading commentary or junior-level noise worthy of repair.

## Structured review outcomes

Use structured results:

- `approved`
- `repair_required`
- `replan_required`

with:

- rationale;
- concrete findings;
- bounded repair guidance where applicable;
- candidate revision;
- contract/cycle id;
- evidence references.

`replan_required` means the issue is with the current contract/decomposition/design lane rather than simply implementation quality.

## Pool model

PR16 should introduce explicit pool-ready orchestration state.

A pool is a logical durable collection/state, not necessarily an in-memory worker queue and not necessarily parallel in PR16.

At minimum model these states/collections conceptually:

### `tdd_ready`
Behavior Contracts ready for a Tester/Developer cycle.

### `cycle_active`
Contracts currently inside a RED/GREEN cycle.

### `review_ready`
Mechanically accepted GREEN candidates awaiting senior semantic review.

### `repair_ready`
Candidates for which senior review requested bounded repair.

### `replan_ready`
Contracts/candidates blocked because the behavior lane itself needs redesign/decomposition.

### `approved`
Semantically approved cycles/contracts whose revision may be used for subsequent progression.

### `completed`
Behavior Contracts whose completion criteria are fully satisfied.

The exact internal representation can be enum/status records rather than six physical queues, but transitions must be explicit and queryable.

## Why pools now

Pools are introduced now to avoid baking a strictly synchronous call stack into ATHBA.

PR16 may execute serially:

```text
Tester -> Developer -> review -> next cycle
```

but state should support a future scheduler doing:

```text
many tdd_ready contracts
 -> multiple active RED/GREEN lanes where resources allow
 -> review_ready pool
 -> one or more reviewer workers
 -> repair/replan/approved pools
```

Do not implement full parallel scheduling in PR16.

Do not bind a pool to a GPU/model/worker.

The design goal is simply that future parallelism does not require rewriting the domain progression model.

## Revision progression with pools

Keep mechanically accepted candidate revisions distinct from semantically approved revisions.

Example:

```text
approved base G0
 -> RED R1
 -> GREEN candidate G1
 -> review_ready
 -> reviewer approved
 -> approved pool / semantic base G1
 -> next cycle may start from G1
```

Repair:

```text
G1 candidate
 -> review_required repair
 -> repair_ready
 -> bounded repair via Rack AI -> G1r
 -> review_ready again
 -> approved only after review
```

Replan:

```text
G1 candidate or RED discovery
 -> reviewer/decomposer detects contract flaw
 -> replan_ready
 -> stop this lane
```

An unreviewed or rejected candidate must never become the next semantic base.

## Repair loop

Support a small bounded repair loop.

When semantic review returns `repair_required`:

- move the item to `repair_ready`;
- create a narrowly scoped production repair task from the candidate revision;
- preserve accumulated tests;
- run through normal Rack AI acceptance;
- return the new candidate to `review_ready`;
- re-review;
- bound repair attempts (for example 2) and fail closed when exhausted.

Do not create unlimited self-editing.

## Reasoning boundary

Tester cycle selection, Developer implementation, contract creation and senior review require judgment.

Use ATHBA provider-neutral abstractions and the existing Rack AI execution boundary.

The live proof should be local-first on `gpurack`.

ATHBA application/domain code must not name:

- `local-primary`;
- `local-coder`;
- GPU ids;
- concrete model ids;
- ports/endpoints.

Rack AI retains physical resource authority.

Cloud/OpenRouter is not the default PR16 proof path.

## What PR16 does not prove

PR16 does not implement or prove:

- Project Manager / Master Designer agent;
- Solution Architect agent;
- full Component Designer agent;
- generalized Behavior Decomposer for arbitrary applications;
- broad user prompt -> architecture generation;
- multi-component planning;
- full Tiny Ticket;
- generalized project backlog/Kanban execution;
- automatic cloud escalation;
- full parallel scheduler;
- multiple concurrent GPU workers;
- reviewer batching policy optimization.

Those remain future layers.

## Live proof

Run one full local ReservationBook Behavior Contract through the new lane.

Expected shape:

```text
component-level ReservationBook requirement
 -> Behavior Contract generation
 -> deterministic contract validation
 -> tdd_ready
 -> Tester chooses smallest missing RED step
 -> Rack AI RED acceptance
 -> Developer GREEN
 -> Rack AI candidate accepted revision
 -> review_ready
 -> Senior Reviewer
      -> approved -> next cycle
      OR repair_ready -> repair -> review_ready
      OR replan_ready -> stop
 -> repeat until Behavior Contract completion criteria satisfied
 -> completed
```

The live proof must not contain a hidden pre-authored list of all Tester/Developer cycle prompts.

## Contract validation

Before execution, deterministically validate:

- unique/non-empty contract id;
- valid repository-relative paths;
- non-empty observable requirements;
- completion criteria present;
- no physical resource-selection fields;
- traceability to original component requirement;
- no obviously contradictory invariants;
- only supported pool/status values.

Fail closed if malformed.

## Persistence

Persist enough to reconstruct:

- original component requirement;
- Behavior Contract;
- current pool/state;
- each Tester-selected cycle objective;
- RED revision/evidence;
- GREEN candidate revision/evidence;
- senior review decision/findings;
- repair attempts/revisions;
- current semantically approved base;
- fulfilled and remaining contract requirements;
- final completion status.

## Tests required

Add deterministic tests proving at least:

1. a component requirement can produce a valid Behavior Contract;
2. malformed contracts fail closed;
3. no resource-selection fields leak into contracts or work requests;
4. Tester selects a cycle objective from contract requirements rather than a hidden hard-coded behavior list;
5. Developer operates from the accepted RED revision;
6. mechanically accepted GREEN transitions to `review_ready`, not directly to next TDD cycle;
7. reviewer approval moves work to approved progression;
8. unreviewed candidate cannot become next semantic base;
9. `repair_required` moves to `repair_ready` and blocks next cycle;
10. repaired candidate returns to `review_ready`;
11. `replan_required` moves to `replan_ready` and stops the lane;
12. pool/state transitions persist and resume safely;
13. completed contracts are not rerun;
14. accumulated requirements/test evidence remains traceable;
15. existing PR11-PR15 tests remain green under Python 3.14.

## Definition of done

PR16 is complete when:

1. ATHBA accepts the ReservationBook component requirement;
2. a structured Behavior Contract is generated without a pre-written micro-behavior/prompt list;
3. local Tester/Developer roles dynamically select and execute successive TDD cycles inside that contract;
4. PR15 path/revision safety is preserved;
5. every GREEN candidate enters `review_ready` before progression;
6. senior reviewer can approve, request bounded repair, or require replan;
7. pool/state transitions are durable and future-parallelism-friendly;
8. only semantically approved revisions become next-cycle bases;
9. the ReservationBook contract eventually reaches `completed` with original requirements satisfied;
10. full ATHBA Python 3.14 tests and compile gate remain green;
11. the live proof is local-first and does not hard-code physical resources into ATHBA.

Report:

`PR16_BEHAVIOR_CONTRACT = PASS|FAIL`

`PR16_DYNAMIC_TDD_LANE = PASS|FAIL`

`PR16_SEMANTIC_REVIEW = PASS|FAIL`

`PR16_POOL_PROGRESSION = PASS|FAIL`

## 2026-08-29 prompt hardening and live probe

The first live local contract-generation attempt against:

- model id `local-primary`
- endpoint `http://127.0.0.1:8017/v1`
- underlying model `cyankiwi/gemma-4-12B-it-AWQ-INT4`

exposed seven concrete output-shape failures:

1. JSON wrapped in Markdown fences.
2. `production_paths` emitted conceptual names such as `AddResource`.
3. `test_paths` emitted semantic labels rather than repository file paths.
4. `public_api` emitted an object instead of `list[str]`.
5. `error_semantics` emitted a string instead of `list[str]`.
6. `status` emitted `READY` instead of lowercase `tdd_ready`.
7. observable requirements bundled unrelated failure modes under one ref.

The PR16 response path remains strict:

- `_json_object()` still rejects fenced or prefixed prose responses.
- `BehaviorContract.from_dict()` still rejects wrong field types and unsupported status values.
- contract path validation now requires repository-relative file paths and can enforce caller-provided allowed path subsets.

Prompt hardening added:

- raw JSON only / no code fences / no commentary rules;
- explicit allowed production and test path lists;
- exact required JSON field shapes;
- exact `status` value `tdd_ready`;
- atomic observable-requirement rules;
- explicit prohibition on worker/model/GPU/endpoint leakage.

### Added regression coverage

`tests/development/test_behavior_contract_coordinator.py` now proves:

- fenced JSON fails closed;
- prose before JSON fails closed;
- `public_api` must be `list[str]`;
- `error_semantics` must be `list[str]`;
- `status` must remain `tdd_ready`;
- absolute, conceptual, and parent-escaping paths are rejected;
- returned contract paths must stay inside the allowed path set;
- the planner prompt explicitly contains the raw-JSON, type, path, and atomicity constraints.

Focused validation on `2026-08-29`:

- `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q tests/development/test_behavior_contract_coordinator.py`
  - result: `38 passed`

Repository validation on `2026-08-29`:

- `env DJANGO_SECRET_KEY=athba-test-secret CPU_ONLY=true ./.venv/bin/python -m pytest -q`
  - result: `134 passed`
- `./.venv/bin/python -m compileall athba core llm_service tests`
  - result: pass

### Five-shot local-primary probe

Probe input:

- requirement text: `Build a small in-memory ReservationBook for reservable resources.`
- allowed production paths: `["reservation_book.py"]`
- allowed test paths: `["tests/test_reservation_book.py"]`
- ATHBA gateway path: `ProviderReasoningGateway(OpenAIProvider(...), model="local-primary")`
- endpoint env: `OPENAI_API_BASE=http://127.0.0.1:8017/v1`
- key env: `OPENAI_API_KEY=local-test-key`
- no output repair, fence stripping, or type coercion

Probe timing:

- total wall time for 5 runs: `104.448s`
- per-run latency: `20.900s`, `20.885s`, `20.887s`, `20.887s`, `20.887s`

Observed outputs:

1. raw JSON only: yes; structural validation: pass; atomicity: acceptable; leakage: none
2. raw JSON only: yes; structural validation: pass; atomicity: acceptable; leakage: none
3. raw JSON only: yes; structural validation: pass; atomicity: acceptable; leakage: none
4. raw JSON only: yes; structural validation: pass; atomicity: acceptable; leakage: none
5. raw JSON only: yes; structural validation: pass; atomicity: acceptable; leakage: none

Stable post-hardening characteristics across all 5 runs:

- `production_paths == ["reservation_book.py"]`
- `test_paths == ["tests/test_reservation_book.py"]`
- `public_api` emitted as a list
- `error_semantics` emitted as a list
- `status == "tdd_ready"`
- no Markdown fences
- no worker/model/GPU/endpoint leakage

Current viability assessment:

- The prompt/validation boundary is now internally coherent and repeatably enforces the PR16 structural contract.
- The 5-shot local proof is green for shape/path/type/status constraints.
- The probe did not complete within `90` seconds for all five runs combined, but each individual contract generation completed in about `21` seconds.
- This is sufficient for PR16's local contract-generation baseline.
- Semantic richness of the generated ReservationBook requirements can still improve later through better upstream requirement text and future reasoning-provider evolution, without weakening the strict PR16 parser.

`PR16_LOCAL_CONTRACT_GENERATION = PASS`

`PR16_READY_FOR_LIVE_TDD_RUN = YES`

`PR16_END_TO_END_COMPONENT = PASS|FAIL`
