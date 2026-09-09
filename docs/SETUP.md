# ATHBA Setup

Date: 2026-08-30

## Purpose

This setup guide covers the current `/srv/ATHBA` repository state on the `pr17-specification-gatekeeper` branch. It is intentionally aligned with the modern ATHBA versus Rack AI boundary.

## Prerequisites

- Python `^3.14`
- Poetry `2.4.1`
- A `.env` file based on `.env.example`
- Mongo credentials only if you exercise Mongo-backed paths

## Install

```bash
poetry install --sync
cp .env.example .env
poetry run python manage.py migrate
```

## Environment contract

Required baseline:

```env
DJANGO_SECRET_KEY=replace-me
DEBUG=false
CPU_ONLY=true
```

Mongo-backed paths use:

```env
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_DB_NAME=ai_platform
MONGO_USER=athba
MONGO_PASS=replace-me
```

Optional reasoning-provider settings:

```env
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
```

`LLM_SERVER_URL` remains only for the quarantined legacy compatibility stack.

## Validation-first setup check

```bash
poetry run python scripts/check_coding_principles.py
poetry run mypy
poetry run python -m compileall athba core llm_service tests scripts
poetry run pytest -q
```

## Authority references

- `docs/ATHBA_RACK_AI_ARCHITECTURE.md`
- `docs/pre_pr17_architecture_quarantine.md`
- `docs/pr17-specification-gatekeeper.md`
