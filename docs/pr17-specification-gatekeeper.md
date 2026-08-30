# PR17 — Specification Gatekeeper and executable-specification coverage

## Goal

Add the next ATHBA development-semantics layer identified by PR16: an independent **Specification Gatekeeper** that maintains a meticulous checklist of individually verifiable specification obligations and refuses requirement completion until each applicable item is proven by accepted test evidence.

PR17 builds on PR16. It does not redesign Rack AI and does not implement the future full Project Manager, Solution Architect, or generalized application-design layers.

## Why PR17 exists

PR16 proved that the local 12B model can understand bounded component requirements, obey strict schemas, and operate usefully inside a TDD-oriented lane. It also showed a repeatable limitation: when asked to independently compress a complete requirement into a Behavior Contract, the model can omit source obligations even while producing structurally valid output.

PR16's source-requirement traceability correctly detects that semantic loss and fails closed.

PR17 therefore separates implementation planning from independent specification-completeness verification.

## Core architecture

```text
higher-level design / component requirement
        |
        +------------------------------+
        |                              |
        v                              v
Behavior Planner                Specification Gatekeeper
        |                              |
        |                       independent checklist
        v                              |
Tester RED <-> Developer GREEN         |
        |                              |
        v                              |
Senior Reviewer                       |
        |                              |
        +-------------> Gatekeeper verification
                                |
                    +-----------+-----------+
                    |                       |
                    v                       v
             all checklist             missing test
             items proven              evidence
                    |                       |
                    v                       v
               requirement            targeted gap
                complete              back to TDD lane
```

The Behavior Planner should initially receive the component requirement, not the complete Gatekeeper checklist. The checklist is an independent acceptance ledger intended to reduce correlated planning and verification blind spots.

## Specification atomization

For each component-level requirement, the Gatekeeper first creates a detailed checklist of individually verifiable obligations.

A sentence such as:

> A resource has a unique id and a positive integer capacity.

may atomize into obligations equivalent to:

- a resource has an id;
- the resource id is unique;
- a resource has capacity;
- capacity is an integer;
- capacity is positive.

This process must be generic and must not hard-code ReservationBook-specific requirements into ATHBA.

The existing `SourceRequirementClause` work from PR16 is expected to be reused or evolved rather than discarded without reason.

## Test suite as executable specification

The Gatekeeper should not primarily inspect production source and decide that code appears to implement a checklist item.

The central verification question is:

> Which accepted test or tests prove this specification item?

A checklist item cannot be marked complete from an LLM's bare assertion.

`proven` must be backed by concrete evidence such as:

- test/node identity;
- TDD step or requirement reference;
- accepted RED/GREEN history;
- semantically approved revision;
- Rack AI evidence reference where available.

Where evidence is absent, the item remains unresolved even if production code appears likely to satisfy it.

## Gatekeeper outcomes

A minimal assessment vocabulary should support concepts equivalent to:

- `proven`
- `missing_test_evidence`
- `uncertain`

A missing item should yield a structured targeted gap that can be fed back into the existing TDD lane.

A gap should identify at least:

- checklist item ref;
- obligation text;
- why current accepted test evidence is insufficient;
- expected proof target;
- traceability to the component requirement.

The gap is not itself a pre-authored implementation prompt. The existing Tester/Developer lane decides how to establish the missing executable proof.

## Relationship to Senior Reviewer

The Senior Reviewer and Specification Gatekeeper have different jobs.

Senior Reviewer asks:

> Is this mechanically accepted candidate good implementation code for the intended behavior/design?

Specification Gatekeeper asks:

> Does the accepted executable test suite prove every obligation in the component specification?

A candidate may be clean, idiomatic and semantically approved while the overall requirement still remains incomplete because checklist evidence is missing.

## Relationship to Rack AI

Rack AI remains unchanged in responsibility.

Rack AI owns:

- physical worker/model/GPU selection;
- repository registration and isolated worktrees;
- path policy;
- command execution and limits;
- deterministic acceptance;
- trusted revisions and evidence.

ATHBA owns the Gatekeeper, checklist, TDD semantics and completion logic.

No Gatekeeper domain/application object should contain physical worker/model/GPU selection.

## PR17 proving target

Continue using the disposable Python 3.14 ReservationBook component as a proving fixture, because its original component requirement contains both happy-path, validation, invariant and state-preservation obligations.

PR17 should prove that a checklist can represent obligations such as:

- successful resource addition;
- resource-id uniqueness;
- positive integer capacity;
- successful reservation creation;
- reservation-id uniqueness;
- known-resource validation;
- positive reservation quantity;
- capacity limit;
- cancellation;
- unknown cancellation;
- availability query;
- cancellation restoring capacity;
- state preservation on failed operations.

Do not hard-code this exact list into the generic implementation.

## Persistence

Persist enough to reconstruct:

- original component requirement;
- checklist and checklist refs;
- current assessment status per checklist item;
- accepted test evidence mapped to each item;
- unresolved/uncertain items;
- targeted gaps emitted back toward TDD;
- requirement-level completion status.

## Completion rule

A component requirement may only be considered complete when every applicable Gatekeeper checklist item is `proven` by concrete accepted executable-specification evidence.

Do not allow:

- an LLM assertion alone to close an item;
- a production-code inspection alone to close an item;
- Behavior Contract completion alone to close the component requirement;
- missing or uncertain checklist items to be silently ignored.

## Scope

PR17 should implement the smallest vertical slice necessary to prove:

1. component requirement -> independent atomic checklist;
2. checklist persistence;
3. accepted TDD test evidence -> checklist mapping;
4. deterministic refusal to mark an item proven without concrete evidence;
5. unresolved item -> structured targeted gap;
6. targeted gap can re-enter the existing TDD lane without changing Rack AI;
7. requirement completion only when every applicable checklist item is proven.

## Non-goals

Do not add in PR17:

- Project Manager / Master Designer;
- Solution Architect;
- generalized Component Designer;
- broad user prompt -> full application architecture;
- cloud reasoning as mandatory default;
- Rack AI semantic interpretation;
- full parallel scheduling;
- generalized Kanban/dashboard UI;
- arbitrary production-source semantic proof as a substitute for tests.

## Validation principle

Prefer deterministic evidence mapping wherever possible. Reasoning may assist with checklist atomization and matching candidate tests to obligations, but final `proven` state must be grounded in accepted test/revision evidence and fail closed when evidence cannot be established.

## Definition of done

PR17 is complete when:

- a component requirement can produce a validated independent checklist;
- checklist items are individually verifiable and traceable;
- the checklist remains independent from initial Behavior Planner implementation guidance;
- accepted TDD history can be mapped to checklist items;
- missing proof remains visible;
- missing proof produces a targeted TDD gap;
- a later accepted test can satisfy that gap;
- requirement completion is deterministically blocked until all applicable items are proven;
- existing PR11-PR16 behavior remains green;
- Rack AI's boundary remains unchanged.

Final proof should report:

`PR17_SPECIFICATION_ATOMIZATION = PASS|FAIL`

`PR17_TEST_EVIDENCE_MAPPING = PASS|FAIL`

`PR17_TARGETED_GAP_LOOP = PASS|FAIL`

`PR17_REQUIREMENT_COMPLETION_GATE = PASS|FAIL`

`PR17_LOCAL_GATEKEEPER_VIABLE = YES|NO`

## Live vertical-slice checkpoint (2026-08-29)

The unit-level gatekeeper proof is green. A real local-provider vertical-slice
attempt was also started against the disposable ReservationBook fixture at
`/home/tomp/projects/reservation-book-pr16-fixture`, beginning from
`f45f32cc847ce2c531c6847ff2276a6256f637ad`.

The live path surfaced three ATHBA robustness defects, now covered by focused
regression tests:

- local reasoning can label a quality clause with `evidence_kind: quality`; ATHBA
  now normalizes that compatible alias to review evidence;
- independently generated checklist and contract references can differ despite
  equivalent obligation text; evidence mapping and targeted-gap traceability now
  resolve matching contract clauses without treating ref spelling as semantics;
- local reasoning can return fenced JSON, short pytest names, uncovered contract
  clauses, or a stale requirement ref; the affected planners now make one bounded
  repair request and require a valid, path-bounded pytest node id.

The proof did reach a real Rack AI RED work unit, but it did not produce an
accepted RED revision. Rack AI executed `python3` as `/usr/bin/python3` in the
isolated worktree, where Python 3.14.4 has no `pytest` installed. The deterministic
RED wrapper rejected that environment failure before it could establish an
executable test result. The retained evidence packet is:

`/srv/rack-ai/state/changes/athba-pr17-live-proof--BR-001-STEP-1--red/review-packet.json`

This is not a Gatekeeper PASS claim. PR17 still needs a Rack AI Python 3.14 test


## Repository-aware Tester checkpoint (2026-08-29)

ATHBA now passes bounded, revision-pinned target-repository material to the
dynamic Tester and RED/GREEN work-unit objectives: relevant source and test
paths/content, module names, existing pytest nodes, the trusted revision and
the active requirement reference. External repositories are explicitly kept
free of ATHBA import/path assumptions. For an empty implementation, RED
guidance requires module-level imports and API lookup inside the test body so a
missing API fails during test execution rather than collection.

The Gatekeeper can now select one traceable executable checklist gap and persist
its supplemental `GK-*` requirement as the only active Tester target. A
semantically approved targeted cycle re-assesses that checklist item; it may
leave the component `approved` with further checklist debt, or become
`completed` only if the whole checklist is proven. An untraceable executable
checklist item fails closed instead of silently falling back to an unrelated
ordinary requirement.

### Real local attempt

The fixture was clean at
`f45f32cc847ce2c531c6847ff2276a6256f637ad`. Local `local-primary` produced a
17-item component checklist and a repository-aware Tester proposal. The RED
proposal used collection-safe access to the empty `reservation_book` module and
the intended test executed with the expected `AttributeError` for the missing
`ReservationBook` API.

Rack AI rejected the RED before accepting a revision:

- change id: `athba-pr17-targeted-live-proof--test_duplicate_resource_id--red`
- evidence: `/srv/rack-ai/state/changes/athba-pr17-targeted-live-proof--test_duplicate_resource_id--red/review-packet.json`
- status: `path_policy_failed`
- reason: pytest generated `__pycache__/` and `tests/__pycache__/`, which Rack
  AI treated as changed paths outside the allowed test path.

ATHBA persisted the rejected RED and did not start GREEN. This is a Rack AI
path-policy/runtime concern. ATHBA did not modify Rack AI and the live proof is
blocked until the Rack AI worker resolves that external execution defect.

## Independent planning and test-only reconciliation checkpoint (2026-08-29)

PR17 now keeps three concerns separate:

```text
Architectural requirement
    ├── Gatekeeper atomizer -> independent factual checklist
    └── Behavior Planner -> Tester -> Developer -> Senior Reviewer

final accepted tests + independent checklist
    -> test-evidence reconciliation -> YES / NO per checklist item
```

The atomizer emits only `ref`, `text`, and factual `kind`. It does not choose
tests, reviews, mechanical checks, or any other proof method. The Behavior
Planner receives the original requirement and bounded repository material, but
not the Gatekeeper checklist.

`TestEvidenceReconciler` is a separate post-run process. It accepts `YES` only
when the selected pytest node exists in final source and is traceable to an
accepted RED/GREEN cycle with a semantic revision. `NO` is valid, remains
visible, and never triggers more TDD work. Invented test nodes fail closed to
`NO`.

ATHBA now supplies its Python/pytest runtime in work-unit acceptance commands.
The default Python runtime disables bytecode and pytest cache creation so test
execution remains compatible with the generic executor's path policy. Rack AI
continues to receive only generic commands and paths; it is not taught Python,
pytest, or ReservationBook semantics.

### Clean-run evidence

The first fresh target at
`/srv/ATHBA/state/pr17-independent-runs/pr17-independent-20260829T181500Z/reservation-book`
exposed and repaired an ATHBA defect: repository-material rendering rejected a
missing initial test file instead of representing it as empty TDD material.

Two subsequent fresh targets reached independent Gatekeeper atomization, then
were blocked before TDD execution when the real local `local-primary` provider
timed out while generating Behavior Planner source clauses:

- `/srv/ATHBA/state/pr17-independent-runs/pr17-independent-20260829T182200Z/evidence.json`
- `/srv/ATHBA/state/pr17-independent-runs/pr17-independent-20260829T182600Z/evidence.json`

No Rack AI work unit was submitted in those retries, and no Rack AI files,
configuration, or runtime images were modified. The end-to-end proof remains
incomplete until the local reasoning service can return the Behavior Planner
response reliably.

## PR19 lifecycle end-to-end attempt (2026-08-29)

The PR17 proof runner now creates its ReservationBook project through
`ProjectEnvironmentService` under `/srv/ATHBA/state/projects`, records the
prepared seed revision, and persists every accepted Rack AI revision before the
TDD lane progresses. It retains the project and evidence rather than retiring
the proof target.

Run `pr17-e2e-20260829T221000Z` independently generated a Gatekeeper
checklist and a Behavior Contract from the same requirement. The Behavior
Planner was not given the checklist. Its first RED proposal targeted
`tests/test_reservation_book.py::test_add_duplicate_resource_id`.

Rack AI rejected the generic acceptance request before worktree execution:
`acceptance command must use an approved program name`. The command began with
the ATHBA-owned project runtime `/srv/ATHBA/.venv/bin/python`. No RED revision
was accepted, so ATHBA correctly did not start GREEN, Senior Review, or final
test-evidence reconciliation. The retained ATHBA evidence is
`state/pr17-independent-runs/pr17-e2e-20260829T221000Z/evidence.json`.

This is a Rack AI generic execution capability handoff, not a reason to change
Rack AI from ATHBA or to weaken the project runtime/readiness contract.

## Environment-resource retry (2026-08-30)

Rack AI PR28 then deployed generic `environment_resources` handoff and trusted
the ATHBA-owned `/srv/ATHBA/.venv` resource. ATHBA records this resource on the
project runtime and forwards it through the generic change request without
encoding Python or pytest semantics in the Rack AI adapter.

Fresh run `pr17-e2e-20260830T000100Z` created its project through PR19,
generated an independent 18-item Gatekeeper checklist and an independent
11-requirement Behavior Contract, then submitted the first Tester RED step.
The earlier approved-program failure did not recur: Rack AI mounted the declared
runtime resource and began isolated execution of the ATHBA runtime.

Rack AI rejected that RED before acceptance with `path_policy_failed` because
the implementation created `tests/`, reported as outside the single allowed
test-file path. No RED revision was accepted, so ATHBA did not begin GREEN,
Senior Review, or reconciliation. Evidence is retained at
`state/pr17-independent-runs/pr17-e2e-20260830T000100Z/evidence.json`; the
Rack AI packet is
`/srv/rack-ai/state/changes/pr17-e2e-20260830T000100Z--test_add_duplicate_resource_id--red/review-packet.json`.

This is a further Rack AI generic execution-policy handoff. ATHBA did not alter
Rack AI, weaken allowed-path semantics, or fabricate an accepted revision.

## Accepted-revision progression attempt (2026-08-30)

Fresh run `pr17-e2e-20260830T001500Z` again created a disposable project through
the PR19 lifecycle, with the ATHBA-owned `/srv/ATHBA/.venv` declared as a
generic environment resource. It generated the Gatekeeper checklist and
Behavior Contract independently from the same ReservationBook requirement.

The first RED step, `tests/test_reservation_book.py::test_add_duplicate_resource_id`,
was accepted by Rack AI at `6001a22d2056d7d44f1e11e4449c09010fbbb565`. ATHBA
verified that commit in the project repository, persisted it as the trusted
revision, and submitted GREEN from that exact revision. Rack AI then rejected
the GREEN request before execution with `base sha does not match the registered
repository baseline`.

The returned RED commit is not the seed SHA and ATHBA did not reuse the seed.
The blocker is Rack AI's generic accepted-revision/baseline progression: it
does not yet accept the revision that it returned as accepted for the next
bounded change in the same dynamic project. No GREEN candidate, Senior Review,
or test-evidence reconciliation can be truthfully produced. ATHBA did not
modify Rack AI, alter its path policy, or substitute a revision.

The ATHBA-owned evidence is
`state/pr17-independent-runs/pr17-e2e-20260830T001500Z/evidence.json`. The
proof runner now also retains each serialized generic Rack AI request together
with its returned result or transport error, because the CLI adapter's temporary
request file is deliberately removed after execution.
