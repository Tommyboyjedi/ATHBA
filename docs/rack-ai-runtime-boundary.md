# ATHBA / Rack AI Development Runtime Boundary

## Architectural invariant

ATHBA owns the development environment of the software it builds.

Rack AI is **language- and framework-agnostic** and remains the physical/trust execution authority for the rack.

This boundary is hard. A missing runtime, package, test runner, generated-file convention, or build tool must not cause language-specific development knowledge to leak into Rack AI.

## ATHBA responsibilities

ATHBA owns software-development semantics, including:

- application/project requirements;
- architecture and component design;
- specification decomposition and Gatekeeper checklists;
- TDD strategy and Tester/Developer objectives;
- Senior Review and semantic progression;
- project-specific development environment definition;
- runtime/toolchain and version selection;
- dependencies and package-manager requirements;
- test runner and test commands;
- build commands;
- project-specific environment variables;
- generated/ignored paths;
- persistent or semi-persistent development environments;
- environment implementation choices such as Docker/Podman/devcontainers, virtual environments, Nix, or other mechanisms.

ATHBA may choose a long-lived or semi-persistent environment for an application so that each RED/GREEN cycle does not need to create a new container or reinstall a complete toolchain.

## Rack AI responsibilities

Rack AI owns generic execution/trust concerns only. ATHBA may request that Rack AI:

- allocate a worker/model/GPU or other rack resource;
- use a registered repository and trusted revision;
- create/use an isolated workspace;
- execute a bounded command in an environment supplied/selected by ATHBA;
- enforce allowed paths, declared generated/ignored paths, network policy, timeouts, and resource limits;
- capture stdout/stderr/exit status/revisions/evidence;
- return deterministic acceptance or rejection.

ATHBA should not require Rack AI to understand what language or framework is inside the environment.

## What ATHBA must not delegate to Rack AI

ATHBA must not solve its own development-environment responsibility by teaching Rack AI language-specific rules.

Examples that belong in ATHBA/project environment configuration, not Rack AI Rust code:

- Python requires pytest;
- Python version selection;
- `__pycache__` or `.pytest_cache` conventions;
- Node/npm/pnpm tooling;
- `node_modules` or coverage conventions;
- Rust/cargo project semantics and `target/` conventions;
- .NET SDK versions and `dotnet test` semantics;
- framework dependency installation;
- application-specific build/test strategy.

## Project environment model

ATHBA should evolve toward an explicit per-project development-environment description.

Conceptually it may contain:

```text
project
  runtime/toolchain
  version
  dependencies
  package manager
  test command(s)
  build command(s)
  environment variables
  generated/ignored paths
  environment identity/location
```

The exact representation is future ATHBA design work. It must remain project/software-development state rather than Rack AI domain state.

A project may have a persistent or semi-persistent environment such as:

```text
ATHBA project
  repository/workspace
  development environment
  test/build tooling
```

Rack AI interacts with that environment generically when ATHBA requests execution.

## Desired execution relationship

```text
ATHBA
  -> understands what software is being built
  -> defines/owns its development environment
  -> supplies bounded work + environment/policy information

Rack AI
  -> understands rack resources and trust boundaries
  -> executes the bounded request safely
  -> returns evidence and trusted revisions
```

A future contract between the systems may include generic fields such as:

- environment/profile identifier;
- command argv;
- working directory;
- allowed paths;
- generated/ignored paths;
- network/resource limits.

ATHBA supplies the language-specific values. Rack AI enforces them without interpreting their language semantics.

## Generated paths

ATHBA/project environment configuration owns knowledge of generated paths.

For example, ATHBA may declare `__pycache__/` for a Python project or `target/` for a Rust project. Rack AI should simply enforce the declared generic path policy and must not need to know why those paths exist.

## Failure handoff

ATHBA must not edit Rack AI to unblock an application-development task.

If Rack AI cannot satisfy a generic execution request, ATHBA should persist its state and hand the Rack AI evidence to the Rack AI owner.

Conversely, Rack AI must not edit ATHBA or repair application/test semantics. If a requested environment, command, test, or project policy is wrong, Rack AI returns evidence and ATHBA owns the correction.

Neither worker may cross repository ownership boundaries to unblock itself.

## Consequence for PR17 and future work

The Specification Gatekeeper remains an ATHBA concern. Its checklist, test-evidence mapping, targeted gaps, TDD progression, and project development environment belong on the ATHBA side.

Any tactical work that placed Python/pytest-specific runtime provisioning into Rack AI should not be treated as the target architecture. Future PR17 work must assume this boundary and design the development environment accordingly.

This document is the authoritative architectural invariant for ATHBA's relationship with Rack AI development runtimes.