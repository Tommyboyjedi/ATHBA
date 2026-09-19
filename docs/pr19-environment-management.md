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


## Implemented ATHBA lifecycle

`ProjectEnvironmentService` creates and persists generated projects below
`state/projects/<project-id>/repository`. A project records its repository root,
default ref, trusted base SHA, runtime descriptor, ATHBA runtime location, test
command, generated paths, and lifecycle state (`created`, `prepared`, `ready`,
or `retired`).

For the current Python proof profile ATHBA supplies Python 3.14 and pytest from
its owned runtime. Readiness deterministically verifies the Git repository,
trusted revision, runtime executable, and `pytest --version`. Reloading the
same project id returns the persisted ready project; it does not recreate the
repository or runtime. Retirement is bounded to roots below ATHBA's project
root.

The resulting `RepositoryBinding` contains only generic repository identity,
root, ref, and revision. Runtime details remain in ATHBA and are not added to
Rack AI request fields.

## PR28 integration dependency

PR19 deliberately does not prescribe a Rack AI repository-registration
mechanism. The live bounded-execution smoke remains blocked until Rack AI PR28
provides its supported trusted dynamic-workspace interface. ATHBA will then use
that generic interface without modifying Rack AI configuration or encoding
language/framework meaning in Rack AI.


## Environment lifetime and PR28 dynamic roots

ATHBA owns environment lifetime. `ProjectRuntime.lifetime` distinguishes shared
tooling from future project-persistent or disposable runtimes; the current
`/srv/ATHBA/.venv/bin/python` profile is shared and cannot be removed by
project retirement. `DevelopmentProject.workspace_lifetime` records the
repository/workspace policy. The current generated proof workspace is
disposable and may be explicitly removed only after canonical containment under
ATHBA's project root is verified.

PR28 dynamic projects use generic `repository.id`, `repository.root`,
`base_ref`, and `base_sha` in the existing change request. No runtime,
framework, or application semantics are sent to Rack AI.

## Live environment proof

The earlier deployment prerequisite was resolved externally. At the time of
this proof the deployed Rack AI checkout was `f425063` on
`pr28-trusted-dynamic-workspaces`, and its administrator-owned configuration
authorized `/srv/ATHBA/state/projects` as a trusted dynamic parent root.

On 2026-08-29 ATHBA created
`pr19-live-proof-20260829T210153Z` through `ProjectEnvironmentService` and
submitted one generic, path-bounded marker-file work unit through
`RackAiCliExecutionGateway`. Rack AI returned `checks_passed` for
`pr19-environment-proof--create-marker`; its required-artifact and exact
content acceptance command both passed.

ATHBA persisted the returned accepted revision in `project.json`, reloaded the
same ready project identity, then retired its disposable repository. The
shared `/srv/ATHBA/.venv/bin/python` Python 3.14 runtime remained available.
The ATHBA-owned evidence record is
`state/projects/pr19-live-proof-20260829T210153Z/live-proof.json`.

Rack AI's retained review packet records the marker as an uncommitted worktree
change and reports the seed SHA as its accepted revision. ATHBA preserves that
returned result verbatim and does not infer that the marker is contained in the
revision. Revision materialization and evidence authority remain Rack AI's
responsibility; this PR neither modifies Rack AI nor introduces a cross-repo
workaround.

## Corrected accepted-revision proof

After Rack AI PR28's accepted-revision materialization fix was deployed at
`83d27086`, ATHBA reran the proof on 2026-08-29 using
`pr19-live-proof-20260829T214439Z`. The seed SHA was
`2ce16d8d37e49342ca486d6e6a42a61d9d217a25`; Rack AI accepted the distinct
commit `abd529b5d0d28732ae153b116575dc33a7efe954`.

The runner now fails closed unless the returned SHA differs from the seed,
resolves as a Git commit, and contains `athba_pr19_marker.txt` with the exact
accepted content. It records those checks in the ATHBA-owned evidence file
before persisting and reloading the trusted revision, then retiring the
disposable workspace. The shared Python 3.14 runtime remains intact.
