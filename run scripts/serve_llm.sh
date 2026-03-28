#!/usr/bin/env bash
set -euo pipefail
poetry run uvicorn llm_service.llm_server:app --host 127.0.0.1 --port 8011 --reload
