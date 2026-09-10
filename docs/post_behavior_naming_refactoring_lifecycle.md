# Post-Behavior Naming Reconciliation and Refactoring Lifecycle

Status: authoritative implementation contract; runtime and validation notes in
[the implementation record](post_behavior_naming_refactoring_implementation.md).

This document supersedes the broader future refactoring design in PR21. It deliberately defines a smaller post-behavior process built around narrow model prompts, unchanged behavioral evidence, trusted revision progression, and two separate concerns: **renaming first, refactoring second**.

## Purpose

After ATHBA has completed the existing behavioral delivery path and the independent Specification Gatekeeper has accepted the result, ATHBA should perform two bounded post-behavior processes before treating that accepted revision as the finished engineering result:

1. reconcile explicit names required by the Behavior with the names actually present in production code; then
2. repeatedly ask whether the production code produced for that accepted behavioral delivery has one worthwhile refactoring opportunity, applying at most one opportunity per pass.

The post-behavior process must not become another architecture, specification, code-review, or TDD system. It exists to correct explicit naming drift and then improve the accepted implementation without changing its behavior.

## Required order

```text
existing behavioral delivery
  -> final independent Specification Gatekeeper YES
  -> behaviorally accepted revision
  -> Naming Assessor
  -> [if required] Renamer
  -> accepted tests + Specification Gatekeeper reconciliation
  -> repeat naming assessment until NO
  -> Refactor Assessor
  -> [if worthwhile] Refactorer
  -> accepted tests + Specification Gatekeeper reconciliation
  -> repeat refactor assessment until NO or bounded stop
  -> post-behavior complete revision
```

Naming always completes before refactoring begins. Refactoring must never be used to correct an explicitly required public/API name.

## Entry invariant

This lifecycle may start only from a revision that the existing behavioral path has already accepted through its final independent Specification Gatekeeper reconciliation.

Persist that exact SHA as the immutable `behaviorally_accepted_revision`. A failed naming or refactoring candidate must never alter that historical fact or advance trusted project state.

ATHBA also persists a `current_post_behavior_revision`. It initially equals `behaviorally_accepted_revision` and advances only after the candidate passes both deterministic accepted-test regression and the existing independent Specification Gatekeeper reconciliation.

No failed candidate is a trusted base.

## Production slice shown to post-behavior models

Models must not receive the whole repository or the full behavioral-development history merely because it is available.

ATHBA derives a focused production slice for the behavioral delivery being processed. The slice is the production code introduced or modified between the trusted entry revision for that behavioral delivery and its Gatekeeper-approved revision, restricted to production paths. Include only the minimum surrounding syntactic context required to understand and edit that code safely.

After an accepted rename or refactor, regenerate the focused slice from the current accepted post-behavior revision so the next assessment sees the current code, not stale code.

Do not include unrelated production modules, previous model transcripts, failed candidates, architecture dossiers, Gatekeeper reasoning, test output, coding-principles prose, or repository history in an assessor prompt.

## Process A: Naming reconciliation

### Responsibility

Naming reconciliation exists only to enforce identifier names explicitly required by the accepted Behavior/Behavior Contract.

It is not a general naming-quality review. The Naming Assessor must not invent a preferred name, apply style conventions, rename private/internal variables for readability, or infer that a different name would be nicer.

Examples of eligible explicit names include a class, public method, function, property, event, command, field, endpoint-facing symbol, or equivalent identifier that the Behavior explicitly requires.

If the Behavior does not explicitly require an identifier name, naming reconciliation has no authority to rename it.

### Naming Assessor input

Keep the input minimal:

- the focused accepted Behavior text needed to establish explicit required identifiers, including its typed `public_api` information when present; and
- the current focused production slice.

Do not provide tests, Gatekeeper findings, development transcripts, architecture documents, coding-principles documents, or unrelated source.

### Naming Assessor output

One assessment returns only one of:

```text
NO
```

or one exact mismatch:

```text
YES
current_name: <identifier currently implemented>
required_name: <identifier explicitly required by Behavior>
```

Return at most one rename per pass. If several mismatches exist they are handled by subsequent passes. This keeps the Renamer's work mechanically narrow.

`NO` is the correct answer when there is no explicit mismatch. The assessor must not manufacture a rename merely because it was asked to assess the code.

### Naming Assessor prompt contract

The runtime prompt should remain short and semantically equivalent to:

> Compare the explicit identifier names required by this Behavior with the production code below. Is one explicitly required public/product identifier implemented under a different name? Do not suggest style improvements or invent better names. Answer NO if there is no exact requirement mismatch. If YES, return only one current_name -> required_name mapping.

Do not expand this prompt with general engineering advice.

### Renamer authority

The Renamer receives:

- the current accepted production code needed to perform the rename;
- the affected accepted tests needed to update references; and
- exactly one `current_name -> required_name` mapping from the Naming Assessor.

The Renamer may modify production code and tests **only insofar as necessary to perform that identifier rename and update references to it**.

It must not:

- change behavior or control flow;
- change values or algorithms;
- add or remove functionality;
- change assertions or expected results;
- add, remove, broaden, weaken, or rewrite test cases;
- perform unrelated cleanup;
- perform a second rename not supplied by the assessor.

A method/function signature may change only in the identifier being renamed. Parameters, return behavior, exceptions, side effects, and other externally observable behavior remain unchanged.

### Naming validation

After each rename candidate:

1. run the unchanged accepted behavioral test suite, except for the mechanically necessary identifier-reference edits made by the rename;
2. require the deterministic suite to pass;
3. run the existing independent Specification Gatekeeper reconciliation against the same accepted behavioral authority;
4. promote the candidate only when both pass;
5. otherwise discard the candidate and retain `current_post_behavior_revision` unchanged.

The Gatekeeper is not given a new naming/quality mission. It performs its existing specification reconciliation against the candidate revision.

After promotion, run Naming Assessor again on the updated focused production slice. Naming completes only when the assessor returns `NO`.

## Process B: Iterative refactoring

### Responsibility

Refactoring begins only after naming reconciliation has returned `NO`.

Its purpose is to find one clear, worthwhile opportunity to make the production code created or changed by the accepted behavioral delivery simpler, less duplicated, more efficient, or more maintainable while preserving the now-correct public/product interface and observable behavior.

It is intentionally not a broad Engineering Quality Gate. There is no large checklist passed to the model and no request to review the entire repository.

### Refactor Assessor input

The Refactor Assessor receives **only the current focused production slice**.

It must not receive:

- tests;
- the Behavior or specification;
- Gatekeeper material;
- architecture documents;
- coding-principles prose;
- prior assessor reasoning;
- prior refactor transcripts;
- unrelated repository source.

The point is to make one narrow structural judgment from the code itself rather than encourage the model to solve extra problems suggested by surrounding context.

### Refactor Assessor output

One assessment returns only one of:

```text
NO
```

or:

```text
YES
objective: <one bounded refactoring objective>
reason: <one brief reason this is materially worthwhile>
```

At most one opportunity is returned per pass.

The assessor must be explicitly biased toward `NO`: marginal stylistic changes, speculative abstractions, theoretical future extensibility, broad redesign, public renaming, behavior changes, test changes, and changes whose value is uncertain are not valid opportunities.

### Refactor Assessor prompt contract

The runtime prompt should remain short and semantically equivalent to:

> Review only the production code below. Is there one clear, worthwhile refactoring that would materially improve simplicity, duplication, efficiency, or maintainability while preserving its public interface and externally observable behavior? Do not propose public renaming, new behavior, test changes, broader architecture work, speculative abstractions, or style-only churn. Answer NO unless the improvement is specific and high-confidence. If YES, return only one bounded objective and one brief reason.

Do not add the Behavior, tests, Gatekeeper output, repository rules, or previous discussion to this prompt.

### Refactorer input and authority

The Refactorer receives:

- the current focused production code; and
- only the assessor's single bounded `objective` as the requested change.

The brief assessor rationale may be persisted as evidence but should not be required in the Refactorer's prompt.

The Refactorer may change internal implementation details needed to satisfy that one objective. Internal variables, private helper methods/functions, decomposition, control structure, and implementation shape are not frozen merely because they existed before refactoring.

The Refactorer must preserve:

- public/product identifiers after naming reconciliation;
- public signatures other than internal implementation details;
- accepted inputs and outputs;
- exceptions/error behavior that is externally observable;
- externally observable side effects;
- all behavior established by the accepted behavioral suite.

The Refactorer must not modify tests, introduce new product behavior, perform a public rename, or perform unrelated cleanup outside the single objective.

### Refactoring validation and iteration

After each refactor candidate:

1. tests are read-only and unchanged;
2. run the complete accepted behavioral/regression suite;
3. require all accepted tests to remain green;
4. run the existing independent Specification Gatekeeper reconciliation against the candidate revision;
5. promote the candidate only when both pass;
6. otherwise discard the candidate and retain the previous accepted `current_post_behavior_revision`;
7. regenerate the focused production slice from the promoted revision;
8. send that current slice back to the Refactor Assessor.

The loop ends when the assessor returns `NO`.

### Bounded-loop safeguard

Because a generative assessor can keep finding work when repeatedly asked, refactoring must also have a deterministic bound.

Initial implementation default: **maximum four promoted refactoring passes for one post-behavior lifecycle**.

A duplicate/substantively identical objective already attempted for the current code must not create an endless new loop. Record it and terminate the autonomous refactoring loop rather than repeatedly submitting the same change.

If the bound is reached while the assessor still says `YES`, retain the latest successfully accepted revision, record `refactor_limit_reached`, and finish the autonomous post-behavior process without retroactively invalidating the behaviorally accepted result. Further cleanup is a later explicit work item or human decision.

A model/execution failure must likewise never roll trusted state forward. Existing ATHBA bounded-attempt and human-intervention policy should be reused rather than inventing an unbounded repair conversation for this lane.

## Test authority

The distinction between the two processes is deliberate:

- **Naming:** tests may be edited only to follow the exact approved identifier rename. Behavioral assertions and expected outcomes are immutable.
- **Refactoring:** tests are completely read-only.

Neither process may weaken behavioral evidence to make a candidate pass.

Any genuinely new or changed product behavior must leave this lifecycle and re-enter ATHBA through the normal specification/Behavior/Tester/Developer/Gatekeeper route.

## State and restart requirements

Persist enough typed state to resume without replaying accepted work or losing the trusted revision chain. At minimum record:

- behavioral delivery/work identity;
- `behaviorally_accepted_revision`;
- `current_post_behavior_revision`;
- focused production-path/slice identity sufficient to reconstruct current input;
- phase: naming or refactoring;
- assessor pass number and typed decision;
- rename mapping or refactor objective when `YES`;
- submission/attempt identity for an executing change;
- candidate revision returned by execution;
- deterministic test evidence;
- Gatekeeper reconciliation evidence/result;
- promotion/rejection outcome;
- refactor promoted-pass count;
- terminal reason (`naming_no_change`, `refactor_no_change`, `refactor_limit_reached`, failure/human intervention as applicable).

On restart, ATHBA reconstructs the next legal transition from persisted state. It must not repeat an already-promoted rename/refactor, re-run an assessor whose durable decision is already awaiting execution, or use a rejected candidate as the next base.

## Agent and execution boundaries

These are ATHBA software-engineering semantics. Rack AI must not learn about Naming Assessor, Renamer, Refactor Assessor, Refactorer, naming phases, refactor phases, or post-behavior state.

Pure assessor reasoning should use ATHBA's approved local-only reasoning path appropriate to the post-seal execution boundary. No cloud model call is permitted after the campaign has entered the local-only execution phase.

Renamer and Refactorer mutations use ATHBA's generic bounded workspace execution port. ATHBA may request broad capability/complexity requirements but must not select a concrete model, worker, GPU, endpoint, or JCode profile. Rack AI receives only an already-ready generic workspace change with exact base revision, paths, objective, limits, and acceptance commands.

Suggested initial routing characteristics are small bounded coding work at low/medium ATHBA priority; concrete placement remains Rack AI policy.

## Required lifecycle states

Exact class names may fit the existing domain model, but the implementation must represent these semantics explicitly rather than burying them in one coordinator conditional:

```text
BEHAVIOR_GATEKEEPER_ACCEPTED

NAMING_ASSESSMENT_PENDING
NAMING_RENAME_PENDING
NAMING_VALIDATION_PENDING
NAMING_COMPLETE

REFACTOR_ASSESSMENT_PENDING
REFACTOR_CHANGE_PENDING
REFACTOR_VALIDATION_PENDING
REFACTOR_COMPLETE

POST_BEHAVIOR_COMPLETE
```

Rejected candidates return to the last trusted `current_post_behavior_revision`; they never become an accepted state transition.

## Required deterministic tests

Implementation must prove at least:

- post-behavior processing cannot start before final Gatekeeper acceptance;
- the immutable behavioral accepted SHA is retained throughout the post-behavior process;
- Naming Assessor receives only focused Behavior naming material plus focused production code;
- Naming Assessor `NO` moves directly to refactoring;
- Naming Assessor `YES` contains exactly one explicit mapping;
- Renamer can write only affected production/tests needed for the exact rename;
- renaming cannot change behavioral assertions or unrelated production logic;
- failed rename tests or Gatekeeper reconciliation do not advance the trusted revision;
- after accepted rename, naming assessment repeats on the new revision;
- Refactor Assessor receives production code only and no tests/spec/Gatekeeper/context leakage;
- Refactor Assessor returns `NO` or one objective only;
- Refactorer receives one objective and cannot write tests;
- failed refactor tests or Gatekeeper reconciliation do not advance trusted state;
- accepted refactor revision becomes the base/slice for the next assessment;
- public/product identifiers cannot be changed by the Refactorer;
- refactor loop terminates on `NO`;
- refactor loop terminates safely at the configured maximum and preserves the last accepted revision;
- duplicate refactor objectives cannot cause an infinite loop;
- persisted state resumes each pending transition without replaying promoted work;
- no Rack AI request contains ATHBA stage names or concrete resource identities;
- no post-seal path can invoke a cloud reasoning provider.

Run the existing full ATHBA test/static/coding-principles gates as regression protection.

## Required live proof

After deterministic implementation is green, run one fresh disposable behavioral delivery through the real local execution path:

```text
behavioral delivery
-> Specification Gatekeeper YES
-> at least one explicit naming mismatch detected
-> exact production + test reference rename
-> tests GREEN
-> Gatekeeper YES
-> naming assessor NO
-> refactor assessor YES
-> one bounded refactor
-> unchanged tests GREEN
-> Gatekeeper YES
-> refactor assessor NO
-> POST_BEHAVIOR_COMPLETE
```

The proof must retain exact revisions and execution provenance for the accepted behavioral baseline, accepted rename, and accepted refactor. No manual edits are permitted between stages.

Also prove the no-work path deterministically: naming `NO`, refactor `NO`, immediate completion from the accepted behavioral revision.

## Explicit non-goals

Do not implement or restore the old PR21 design as part of this work. In particular, do not add:

- a broad Engineering Quality Gate;
- a coding-principles checklist in Refactor Assessor prompts;
- whole-repository semantic review;
- a separate Refactor Reviewer agent;
- test rewriting during refactoring;
- architecture replanning inside the post-behavior lane;
- new behavioral requirements discovered by the refactorer;
- public/API naming suggestions not explicitly grounded in the Behavior;
- direct model/GPU/worker selection in ATHBA;
- Rack AI awareness of software-engineering stages;
- cloud fallback after behavioral execution is sealed local-only;
- unbounded model conversations or refactoring loops.

## Definition of done

This PR's implementation is complete when ATHBA can take a Gatekeeper-approved behavioral revision, correct explicit Behavior-to-code identifier drift through a mechanically constrained naming loop, then perform zero or more one-opportunity-at-a-time refactoring passes against production code only, with unchanged behavioral authority, deterministic regression, Gatekeeper reconciliation, durable restart-safe trusted-revision progression, and a bounded autonomous stop.

The final reported revision is always an accepted revision. Failed post-behavior candidates never replace it.