# PR16 closeout and PR17 Specification Gatekeeper handoff

## Status

PR16 has reached its logical architectural boundary.

It successfully established the lower application-development slice around:

- structured Behavior Contracts;
- dynamic Tester -> Developer RED/GREEN progression;
- explicit candidate versus semantically approved revisions;
- Senior Reviewer outcomes of `approved`, `repair_required`, and `replan_required`;
- durable pool-ready progression;
- bounded repair/re-review;
- strict source-requirement traceability and fail-closed contract admission.

The live local-model experiments also exposed a repeatable planning limitation that should not be hidden by further prompt hardening.

## What the local model proved

`local-primary` / Gemma 4 12B proved capable of:

- understanding the ReservationBook component requirement;
- extracting a detailed source-requirement list;
- obeying strict machine-readable JSON/schema/path constraints after one hardening pass;
- producing mostly focused Behavior Contract requirements;
- operating within a bounded TDD-oriented planning structure.

## What remained unreliable

When independently converting the complete source-requirement set into a Behavior Contract, the model repeatedly omitted some source obligations from observable requirement coverage.

PR16's new deterministic traceability correctly detected that loss and refused to admit the contract to `tdd_ready`.

This is an important success of the safety architecture: semantic omissions are now visible rather than silently becoming incomplete software.

The conclusion is not that Rack AI should understand software requirements. The existing boundary remains unchanged:

### Rack AI

Owns physical/trust execution concerns:

- worker/model/GPU selection;
- repository and worktree isolation;
- path policy;
- commands/timeouts/network;
- deterministic acceptance;
- trusted revisions and evidence.

### ATHBA

Owns software-development semantics:

- specification;
- architecture/decomposition;
- Behavior Contracts;
- TDD planning;
- semantic review;
- project progression and completion.

## Architectural conclusion: Specification Gatekeeper

The next ATHBA layer should be an independent **Specification Gatekeeper**.

For each component-level requirement produced by the future higher planning/design layers, the Gatekeeper first atomizes the prose into a meticulous checklist of individually verifiable specification obligations.

For example, a requirement such as:

> A resource has a unique id and a positive integer capacity.

should yield separate obligations equivalent to:

- a resource has an id;
- the resource id is unique;
- a resource has a capacity;
- capacity is an integer;
- capacity is positive.

The checklist is an independent acceptance ledger, not the Behavior Planner's implementation recipe.

## Test suite as executable specification

Because ATHBA is TDD-driven, the Gatekeeper should not primarily ask whether production code appears to implement each checklist item.

Its primary question should be:

> Which accepted test or tests prove this specification checklist item?

A checklist item is not complete merely because an LLM says `yes`.

Completion should require concrete accepted test evidence such as:

- pytest node id / test identity;
- accepted RED/GREEN cycle traceability;
- semantically approved revision;
- Rack AI evidence reference where available.

The test suite therefore becomes ATHBA's executable specification.

## Independent verification loop

Target lifecycle:

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

The Behavior Planner should initially continue to receive the component requirement rather than the complete Gatekeeper checklist. Keeping the acceptance ledger independent reduces correlated planning/verification blind spots.

## Why PR17 rather than extending PR16

PR16 has already grown from its original proving slice into a substantial Behavior Contract, review, pool-state, and traceability implementation.

The Specification Gatekeeper is a distinct new architectural responsibility with its own state, evidence model, acceptance semantics, and feedback loop.

It should therefore be implemented as PR17 rather than further expanding PR16.

## PR16 disposition

PR16 should be treated as the completed architectural/proving baseline for the lower TDD lane, with one explicit limitation:

- the full unattended ReservationBook component proof is not yet complete because contract semantic completeness correctly fails closed before TDD execution.

That limitation is evidence motivating PR17, not a reason to hide or bypass the check.

## PR17 objective

PR17 should prove the smallest useful Specification Gatekeeper vertical slice:

1. component requirement -> independent atomic specification checklist;
2. checklist persists independently from Behavior Contract/TDD planning;
3. accepted TDD test evidence can be mapped to checklist items;
4. checklist items cannot be marked proven without concrete accepted test evidence;
5. uncovered checklist items become structured targeted gaps;
6. targeted gaps can re-enter the existing TDD lane without redesigning Rack AI;
7. requirement completion requires every applicable checklist item to be proven by accepted executable-specification evidence.

PR17 should not attempt to implement the future full Project Manager, Solution Architect, or generalized application-design layers.
