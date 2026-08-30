# ATHBA

ATHBA is the software-development semantics layer for the GPU-rack workflow. Modern PR17 work lives in ATHBA domain code under `/srv/ATHBA`; Rack AI remains the separate execution system that owns worker selection, worktrees, bounded execution, and trusted candidate materialization.

## Current authority

Read these documents first:
- `docs/ATHBA_RACK_AI_ARCHITECTURE.md`
- `docs/pre_pr17_architecture_quarantine.md`
- `docs/pr17-specification-gatekeeper.md`

Modern PR17 paths use provider-neutral reasoning plus Rack AI execution. The older `llm_service`, local GGUF stack, and `/tmp/athba_repos` Developer/Tester loop remain in the repository only as quarantined compatibility surfaces.

## Requirements

- Python `^3.14`
- Poetry `2.4.1`
- A `.env` file based on `.env.example`
- Mongo credentials only if you are using Mongo-backed paths

## Setup

```bash
poetry install --sync
cp .env.example .env
poetry run python manage.py migrate
```

For CI-style validation or CPU-only local verification:

```bash
export DJANGO_SECRET_KEY=athba-test-secret
export CPU_ONLY=true
export MONGO_USER=test
export MONGO_PASS=test
```

## Validation gates

```bash
poetry run python scripts/check_coding_principles.py
poetry run mypy
poetry run python -m compileall athba core llm_service tests scripts
poetry run pytest -q
```

## Documentation map

- `docs/SETUP.md`: current environment and operator setup
- `docs/TESTING.md`: focused and full validation commands
- `PROJECT_STATE.md`: current repository state
- `DIVERGENCE.md`: active boundary between modern ATHBA and quarantined legacy surfaces
- `docs/pre_pr17_repository_governance.md`: Job 4 governance ledger
