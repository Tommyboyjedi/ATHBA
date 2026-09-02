# ATHBA Agent Instructions

These instructions apply to all AI coding agents working in the ATHBA repository.

## Mandatory reading before work

Before inspecting, planning, editing, testing, or committing code, read and obey:

1. `coding_principles.MD`
2. the current ATHBA architecture and boundary documentation
3. the current PR description and any source-controlled implementation contract relevant to the task

The coding principles are mandatory application-level rules. Do not treat them as style suggestions.

## Repository boundary

Work only in the ATHBA repository and ATHBA-owned disposable project repositories explicitly created for the task.

Do not modify Rack AI source or configuration. If a genuine generic Rack AI capability is missing, stop and report the evidence rather than changing Rack AI from an ATHBA task.

## Architecture boundary

ATHBA owns software-development intelligence and semantics, including project/environment meaning, architecture/specification, Behavior Contracts, Tester/Developer/Senior Reviewer progression, failure interpretation, dependency/prerequisite replanning, semantic review, trusted-project progression, Gatekeeper behavior, and final reconciliation.

Rack AI owns generic rack execution/resource behavior such as model/worker selection, trusted worktrees, bounded process execution, resource/network/path policy, evidence, recovery, and accepted candidate revision materialization.

Do not move language/framework-specific development semantics into Rack AI.

## Coding discipline

All new or changed application-owned code must conform to `coding_principles.MD`.

In particular:

- application-owned classes are limited to 100 executable lines unless the user explicitly approves and the exception is documented;
- constructors and methods accept at most two input parameters, excluding `self`; group larger inputs into typed parameter objects;
- prefer Python `dataclass` parameter/value/state objects; do not use Pydantic for ordinary parameter bags;
- use composition over application-owned inheritance;
- avoid magic numbers and strings; use typed configuration, enums, constants, and value objects;
- prefer SQL for suitable relational data operations when a SQL database is present;
- refactor overgrown objects before adding responsibilities;
- model complex workflows as explicit typed state transitions rather than giant coordinator conditionals.

Do not introduce an exception to these rules without explicit user approval and documented rationale.

## Failure and repair discipline

Do not hard-code a solution to make a demonstration pass.

When autonomous work fails:

- preserve evidence;
- diagnose the failure class;
- provide descriptive rather than prescriptive repair information;
- use bounded retry/replan behavior;
- fail closed when evidence is insufficient;
- do not silently advance trusted state from a failed candidate.

## Change discipline

- Inspect existing architecture and tests before editing.
- Make the smallest coherent architectural change, not merely the smallest line-count patch.
- Add tests for behavior and important failure paths.
- Run focused tests first, then the full applicable suite.
- Run compile/static checks and `git diff --check` where applicable.
- Do not merge unless explicitly instructed.
- Report residual risk and incomplete routes clearly.
