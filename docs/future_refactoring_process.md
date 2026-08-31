# Future Refactoring Process

Status: documented future work only

Dependency: complete and merge PR17 behavioral development / specification-gatekeeper work first.

## Purpose

ATHBA should separate behavioral correctness from engineering-quality compliance.

PR17 is responsible for proving that ATHBA can take a behavioral specification through valid RED creation, GREEN implementation, semantic review, and independent specification Gatekeeper reconciliation.

The future Refactoring Process begins only after a behaviorally approved revision exists.

## Core invariant

Observable behavior is frozen during refactoring.

The accepted behavioral test suite is the authority. Refactoring may change structure, decomposition, naming, internal collaboration, and implementation shape, but must not change externally observable behavior unless a new behavioral requirement is opened through the normal development lane.

## Quality policy

The authoritative engineering policy is `coding_principles.MD` plus deterministic repository/tooling evidence where appropriate.

Do not overload the existing Specification Gatekeeper with structural-quality decisions.

Use two independent completion concepts:

1. Specification Gatekeeper: did accepted tests prove the original specification?
2. Engineering Quality Gate: does the behaviorally approved implementation comply with engineering standards?

Both are required for final engineering completion.

## Proposed lifecycle

Behavior Contract complete
→ independent Specification Gatekeeper reconciliation
→ behaviorally approved baseline
→ Engineering Quality Gate
→ if no findings: quality approved
→ if findings: refactor_ready
→ bounded Refactoring Lane
→ full accepted regression suite
→ Refactor Reviewer
→ Engineering Quality Gate again
→ repeat until quality approved or fail closed.

## Engineering Quality Gate

Prefer deterministic/static evidence wherever possible.

Examples include:

- application-owned class executable-line limit;
- constructor/method parameter-count limits;
- prohibited application-owned inheritance;
- type-check/static-analysis failures;
- repository architecture/path constraints;
- dependency-policy violations;
- other mechanically enforceable rules in `coding_principles.MD`.

Use semantic engineering review only for principles that cannot be established reliably through deterministic evidence, such as responsibility/cohesion judgments.

The gate should emit typed quality findings with concrete evidence rather than implementation recipes.

## Refactoring Lane

Refactoring is not another ordinary RED→GREEN behavior ticket.

Inputs:

- behaviorally approved trusted revision;
- complete accepted regression suite;
- one or more typed Engineering Quality findings.

Rules:

- no new product behavior;
- no silent specification changes;
- all accepted tests remain green;
- path/security/execution policy remains enforced;
- refactor findings are descriptive, not prescriptive where possible;
- Developer may choose the implementation strategy;
- semantic review confirms behavior preservation and structural improvement;
- the Engineering Quality Gate is rerun after each accepted refactor slice.

## Example

If behavioral development ends with an application-owned class containing 127 executable lines while the policy limit is 100:

- behavioral completion is not retroactively rejected;
- the quality gate records the concrete violation;
- a refactoring work item is opened against the behaviorally approved revision;
- Developer restructures the implementation without changing observable behavior;
- full accepted tests must remain green;
- the quality gate reruns and closes the finding only when compliance is proven.

## Test code policy

Production `coding_principles.MD` should not automatically be applied wholesale to Tester-generated tests.

A separate Test Artifact Principles contract should be defined as part of PR17 RED-validity work. Test principles should focus on executable, deterministic, readable behavioral evidence rather than production architecture rules.

## Hard constraints that remain immediate

Some constraints are never deferred to the later refactoring process:

- repository/path/security policy;
- syntax/build validity;
- declared dependency restrictions where contractual;
- accepted-test regressions;
- executor/resource boundaries;
- trusted revision integrity.

These remain execution/development correctness conditions.

## Out of scope until PR17 succeeds

Do not implement the Refactoring Process while PR17 behavioral development proof remains incomplete.

Specifically defer:

- refactoring lifecycle states;
- Engineering Quality Gate implementation;
- coding-principles finding generation;
- Refactor Reviewer;
- quality-approved final state;
- autonomous refactoring execution.

## Future completion target

After PR17 is proven, implement a generic lifecycle where ATHBA can transform:

behaviorally correct + specification-covered code

into:

behaviorally correct + specification-covered + engineering-compliant code

without relying on the Developer to remember and perfectly obey every structural rule during each tiny GREEN implementation step.
