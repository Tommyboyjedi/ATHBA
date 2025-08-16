# Project State Documentation

## Project Overview
**Name**: ATHBA (Agentic AI Team for TDD DevOps Software Development)  
**Type**: Django-based AI application with FastAPI components  
**Description**: A complete TDD DevOps software development agentic AI team implementation.

## Technical Stack
- **Backend Framework**: Django <5.2 with Django Ninja for APIs
- **Database**: SQLite (default), MongoDB (via Motor)
- **AI/ML**: 
  - Ollama integration
  - llama-cpp-python
  - AutoEvals for evaluation
- **APIs**: Django Ninja and FastAPI
- **Async Support**: ASGI with Uvicorn
- **Frontend**: Django Templates with HTMX for interactivity and real-time updates (via SSE)

## Project Structure
```
ATHBA/
├── athba/                  # Django project config
├── core/                   # Main application
│   ├── agents/             # AI agent implementations
│   ├── controllers/        # Business logic controllers
│   ├── dataclasses/        # Data models and schemas
│   ├── datastore/          # Data access layer
│   ├── endpoints/          # API endpoints
│   ├── infra/              # Infrastructure code
│   ├── services/           # Business services
│   └── sse/                # Server-Sent Events
├── http_requests/          # HTTP request templates/examples
├── llm_service/            # LLM integration service
├── static/                 # Static files
└── templates/              # Django templates
```

## Dependencies
Key dependencies (from pyproject.toml):
- Django <5.2
- Django Ninja
- PyMongo & Motor (MongoDB drivers)
- Ollama
- FastAPI & Uvicorn
- llama-cpp-python
- AutoEvals
- psycopg2 (PostgreSQL adapter)

## Configuration
- Uses environment variables via django-environ
- Development settings allow all hosts
- SQLite database by default
- MongoDB connection configured via `MONGO_*` env vars (see `core/infra/mongo.py`)
- Debug mode controlled by `DEBUG` env var

## Running the Project
1. Install dependencies:
   ```bat
   poetry install
   ```
2. Set up environment variables in `.env` file
3. Run migrations (SQLite by default):
   ```bat
   poetry run python manage.py migrate
   ```
4. Start services (Windows):
   - Web (Django via Uvicorn) on http://localhost:8010
     ```bat
     poetry run uvicorn athba.asgi:application --host 0.0.0.0 --port 8010 --reload
     ```
   - LLM Service (FastAPI) on http://localhost:8011
     ```bat
     poetry run uvicorn llm_service.llm_server:app --host 127.0.0.1 --port 8011 --reload
     ```
   - Or use batch files under `run scripts/` (e.g., `dev_up.bat`).

## Notable Features
- AI agent system with multiple agent types
- Support for multiple LLM backends
- API-first architecture
- Real-time updates via SSE
- Evaluation framework for AI outputs

## Development Notes
- Project uses Poetry for dependency management
- Follows a modular architecture with clear separation of concerns
- Includes infrastructure for testing and evaluation
- Supports both synchronous and asynchronous operations

## Next Steps
- Review and complete the specification document
- Set up proper database configuration for production
- Implement CI/CD pipelines
- Add comprehensive documentation
- Set up monitoring and logging
