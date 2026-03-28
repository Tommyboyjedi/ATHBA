#!/usr/bin/env bash
set -euo pipefail
poetry run uvicorn athba.asgi:app --host 0.0.0.0 --port 8000 --reload
