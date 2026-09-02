# AGENTS.md — ATHBA Agent Rules

All coding agents working in this repository must read and obey:

1. `agent.MD`
2. `coding_principles.MD`
3. `docs/athba_rack_ai_workspace_boundary_rationale.md`
4. the current ATHBA architecture/boundary documentation
5. the current PR description and any source-controlled implementation contract relevant to the task

`coding_principles.MD` is mandatory. Its class-size, parameter-count, dataclass, composition-over-inheritance, configuration, SQL, explicit-domain-type, state-transition, and exception rules apply to all new or changed application-owned code.

## ATHBA / Rack AI boundary

ATHBA owns every software-engineering concept: readiness, dependencies, TDD stages, Tester/Developer meaning, attempts, repair, escalation, semantic interpretation, and trusted-revision progression.

Rack AI receives only an already-ready generic bounded workspace request through a replaceable connector. Do not send ATHBA stage names, RED/GREEN meaning, dependency graphs, concrete workers, model IDs, GPUs, endpoints, or JCode profiles across that boundary.

ATHBA may request broad capabilities (`reasoning`, `coding`, `visual`, `audio`), generic complexity, a large-context flag, and only `low` or `medium` rack priority. Machine-enforced repository, path, network, timeout, and acceptance fields are authoritative; prompt prose is not the safety or routing boundary.

This separation exists to keep ATHBA portable to another execution backend and to keep privileged resource/worktree execution centralized rather than duplicated in every client.

Do not modify Rack AI from an ATHBA task. Preserve the ownership boundary described in `agent.MD`, `docs/athba_rack_ai_workspace_boundary_rationale.md`, and the repository architecture documentation.

Do not merge unless explicitly instructed.
