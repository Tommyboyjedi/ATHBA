# ATHBA Agent Instructions

These instructions apply to all AI coding agents working in the ATHBA repository.

## Mandatory reading before work

Before inspecting, planning, editing, testing, or committing code, read and obey:

1. `coding_principles.MD`
2. `docs/athba_rack_ai_workspace_boundary_rationale.md`
3. the current ATHBA architecture and boundary documentation
4. the current PR description and any source-controlled implementation contract relevant to the task

The coding principles are mandatory application-level rules. Do not treat them as style suggestions.

## Repository boundary

Work only in the ATHBA repository and ATHBA-owned disposable project repositories explicitly created for the task.

Do not modify Rack AI source or configuration. If a genuine generic Rack AI capability is missing, stop and report the evidence rather than changing Rack AI from an ATHBA task.

## Architecture boundary

ATHBA owns software-development intelligence and semantics, including project/environment meaning, architecture/specification, Behavior Contracts, Tester/Developer/Senior Reviewer progression, failure interpretation, dependency/prerequisite replanning, semantic review, model-attempt policy, trusted-project progression, Gatekeeper behavior, and final reconciliation.

Rack AI owns generic rack execution/resource behavior such as model/worker selection, trusted worktrees, bounded process execution, resource/network/path policy, evidence, recovery, and accepted candidate revision materialization.

Rack AI must remain language/framework agnostic and ignorant of ATHBA stage semantics.

## Why this boundary exists

Rack AI must not become an ATHBA-specific software-engineering engine, and ATHBA must not become a privileged GPU/worktree execution engine.

Keeping the boundary narrow provides three safeguards:

1. **Replaceability** — ATHBA can use a deterministic fake or another rack backend through the same execution port without rewriting TDD state and progression.
2. **Centralized trust** — worker selection, GPU placement, worktree isolation, path/network/time limits, Git evidence, and terminalization remain in one generic rack service instead of being reimplemented by every client.
3. **Explicit contracts** — security, routing, identity, and acceptance remain typed machine-enforced fields rather than undocumented behavior hidden in prompt text.

The prompt is advisory. The typed execution envelope is authoritative.

## Outbound generic execution contract

ATHBA may internally classify work as scenario authoring, frontier implementation, repair, review, or another software-development stage. Those names do not cross the connector boundary.

For a bounded workspace request, ATHBA may send only generic routing requirements such as:

- broad capabilities: `reasoning`, `coding`, `visual`, `audio`;
- complexity: `small`, `medium`, `large`;
- `requires_large_context`;
- priority from ATHBA: `low` or `medium` only;
- opaque `work_id`, unique `submission_id`, and idempotency data;
- exact repository/base revision;
- allowed paths and authorized read-only resources;
- timeout, network, process, and artifact constraints;
- a bounded objective, immutable context, and deterministic acceptance commands.

ATHBA must not send:

- Tester, Developer, scenario, frontier, RED, GREEN, review, Gatekeeper, or escalation-stage names as Rack AI routing fields;
- ATHBA dependency graphs or semantic readiness rules;
- concrete worker, model, GPU, endpoint, or JCode profile identifiers;
- `high` or `paramount` priority.

Even work that blocks an ATHBA project is at most medium priority to the rack as a whole. High and paramount are reserved for other authorized rack/operator workloads. The ATHBA connector must reject an outbound request above medium.

## Capability request versus Rack AI model metadata

ATHBA sends only what the current job requires, for example `[coding]`, `[reasoning]`, or `[reasoning, coding]`.

Rack AI owns its internal model eligibility and qualification profiles. ATHBA does not author or transmit those profiles. Rack AI may return selection evidence and execution provenance so ATHBA can verify what happened, but ATHBA does not tell Rack AI which worker or GPU to use.

## Queue and attempt ownership

ATHBA owns the authoritative semantic work ledger. It decides readiness and submits only currently dispatchable work. Rack AI queues only already-ready generic jobs and must not infer ATHBA dependencies from IDs or sequence numbers.

A stable `work_id` identifies the same logical ATHBA work. A unique `submission_id` identifies one actual backend model invocation. ATHBA owns attempt and escalation semantics; Rack AI owns the physical execution and evidence for that submission.

Do not hide several semantic model submissions behind one ATHBA submission ID. Low-level infrastructure recovery must remain distinguishable from another model attempt.

## Failure and repair discipline

Do not hard-code a solution to make a demonstration pass.

When autonomous work fails:

- preserve evidence;
- diagnose the failure class;
- provide descriptive rather than prescriptive repair information;
- use bounded retry/replan behavior;
- fail closed when evidence is insufficient;
- do not silently advance trusted state from a failed candidate;
- do not change the connector or Rack AI merely because a model used an unsupported tool or produced an unsupported artifact.

Any further harness change must demonstrate that it restores an existing generic contract rather than merely allowing a live proof to move one step forward. Model output violating a documented contract is not, by itself, evidence that the harness must change.

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

## Change discipline

- Inspect existing architecture and tests before editing.
- Make the smallest coherent architectural change, not merely the smallest line-count patch.
- Add tests for behavior and important failure paths.
- Run focused tests first, then the full applicable suite.
- Run compile/static checks and `git diff --check` where applicable.
- Do not merge unless explicitly instructed.
- Report residual risk and incomplete routes clearly.
