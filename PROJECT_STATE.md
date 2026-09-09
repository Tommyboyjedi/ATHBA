# Project State

Date: 2026-08-30
Branch: `pr17-specification-gatekeeper`
Scope: `/srv/ATHBA`

## Current implementation state

- PR17 is the active development line. ATHBA owns the development semantics: Behavior Contract planning, TDD progression, Gatekeeper checklist state, failure progression, trusted revision continuity, and final test-evidence reconciliation.
- Rack AI is the separate execution authority. ATHBA must not take ownership of worker selection, GPU control, or generic bounded execution policy.
- The repository still contains legacy chat and local-LLM compatibility paths. They are documented and smoke-covered, but they are not the modern PR17 control plane.

## Runtime and toolchain

- Python requirement: `^3.14`
- Dependency manager: Poetry with committed `poetry.lock`
- Primary validation gates: coding-principles AST gate, scoped `mypy`, `compileall`, and full `pytest`
- CI target: CPU-only, no Rack AI mutation, no GPU requirement

## Configuration contract

- Django secret: `DJANGO_SECRET_KEY`
- Debug flag: `DEBUG`
- Legacy compatibility repo root: `DEVOPS_DIR`
- Mongo contract used by `core.infra.mongo`: `MONGO_HOST`, `MONGO_PORT`, `MONGO_DB_NAME`, `MONGO_USER`, `MONGO_PASS`
- Optional provider settings: `OPENAI_*`, `ANTHROPIC_*`
- Legacy local-LLM compatibility only: `LLM_SERVER_URL`

## Active documentation

- `docs/ATHBA_RACK_AI_ARCHITECTURE.md`
- `docs/pre_pr17_architecture_quarantine.md`
- `docs/pr17-specification-gatekeeper.md`
- `docs/pre_pr17_correctness_remediation.md`
- `docs/pre_pr17_trust_hardening.md`
- `docs/pre_pr17_repository_governance.md`
