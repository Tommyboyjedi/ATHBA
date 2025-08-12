# ATHBA

Prerequisites
- Python 3.11
- Poetry

Setup
- poetry env use 3.11
- poetry install
- cp .env.example .env
- Edit .env with strict Mongo credentials (MONGO_USER and MONGO_PASS are required)

Run services
- Start LLM service:
  - ./run\ scripts/serve_llm.sh
- Start web app:
  - ./run\ scripts/serve_web.sh

Notes
- Web ASGI entry: athba.asgi:app (Django mounted under Starlette; SSE/static via Starlette)
- LLM FastAPI app: llm_service.llm_server:app
- Historical Windows BATs remain under "run scripts/"; Linux/macOS scripts mirror their behavior.
