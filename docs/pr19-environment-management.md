# PR19 — ATHBA project environment management

## Purpose

PR19 introduces a focused ATHBA-owned project environment lifecycle before PR17 resumes its end-to-end Gatekeeper proof.

The immediate trigger is a real PR17 run in which ATHBA successfully created a clean generated ReservationBook repository and submitted a bounded RED work unit, but Rack AI rejected the request before execution because the generated repository id was not registered. That exposed an ATHBA project/environment lifecycle gap rather than a Gatekeeper problem.

## Architectural invariant

Read and obey the merged ATHBA runtime ownership documentation before implementation.

ATHBA owns the development environment of software it builds, including:

- project workspace/repository lifecycle;
- runtime/toolchain semantics;
- dependencies/package management;
- test/build commands;
- generated/ephemeral path semantics;
- environment identity and persistence;
- making generated projects available to generic execution infrastructure through supported interfaces.

Rack AI remains language- and framework-agnostic. It owns generic rack-resource allocation, isolated execution, policy enforcement, trusted revisions, and evidence.

ATHBA must not edit Rack AI configuration or files to register or prepare a generated project.

## Goal

Prove a clean lifecycle in which ATHBA can:

1. create a new generated development project;
2. define and persist the project's development environment;
3. prepare any ATHBA-owned runtime/tooling the project needs;
4. make the generated repository available to Rack AI through a generic supported registration/interface mechanism, without direct Rack AI config editing;
5. reuse the same environment/project identity across Tester/Developer/Senior Review cycles;
6. distinguish environment/provisioning failures from semantic planning failures;
7. cleanly tear down or retain the environment according to policy.

## Design direction

PR19 should model a project environment as an ATHBA concept, not a language-specific Rack AI concept.

A future environment may describe Python, Rust, Node/TypeScript, .NET, or another toolchain, but those semantics remain in ATHBA.

Rack AI should receive only generic execution information needed to safely execute work in or against the prepared project/environment.

Do not weaken Rack AI's repository trust boundary by allowing arbitrary unregistered roots merely because ATHBA supplied a path.

If Rack AI lacks a generic registration interface, document that exact interface gap and produce a Rack AI handoff rather than editing Rack AI from the ATHBA worker.

## Scope

PR19 may implement:

- ATHBA project-environment domain/application types;
- environment/project identity persistence;
- clean project creation and reuse;
- ATHBA-owned runtime preparation;
- a provider-neutral/generic repository registration client if Rack AI already exposes a supported registration command/API;
- environment readiness checks;
- explicit environment failure classification;
- deterministic tests and one small integration smoke.

## Non-goals

PR19 does not:

- complete the PR17 Gatekeeper end-to-end proof;
- redesign Rack AI;
- add Python/pytest awareness to Rack AI;
- edit Rack AI configuration directly;
- implement every future language/toolchain;
- implement the future high-level Architect.

## Completion

PR19 is complete when ATHBA can create one clean generated project, establish and persist its development environment, make that project available to Rack AI through a supported generic boundary, execute a minimal generic work-unit smoke, and then reuse the same project/environment identity without manual cross-repository intervention.

After PR19 is complete, PR17 should resume and rerun the full architectural requirement -> Gatekeeper checklist + independent Behavior Planner -> TDD -> Senior Review -> test reconciliation proof.
