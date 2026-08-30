# AGENTS.md — ATHBA Agent Rules

All coding agents working in this repository must read and obey:

1. `agent.MD`
2. `coding_principles.MD`
3. the current ATHBA architecture/boundary documentation
4. the current PR description and any source-controlled implementation contract relevant to the task

`coding_principles.MD` is mandatory. Its class-size, parameter-count, dataclass, composition-over-inheritance, configuration, SQL, explicit-domain-type, state-transition, and exception rules apply to all new or changed application-owned code.

Do not modify Rack AI from an ATHBA task. Preserve the ATHBA/Rack AI ownership boundary described in `agent.MD` and the repository architecture documentation.

Do not merge unless explicitly instructed.
