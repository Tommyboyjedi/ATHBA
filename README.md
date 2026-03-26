# ATHBA - Agentic AI Team for TDD DevOps Software Development

## Overview

**ATHBA** is an AI-powered software development environment that simulates a complete agile team using multiple AI agents. The system orchestrates Project Manager, Architect, Developer, Tester, and Resource Director agents to collaboratively deliver software projects following TDD principles and GitOps workflows.

**Key Features:**
- 🤖 Multi-agent system with specialized roles (PM, Spec Builder, Architect, Resource Director, Dev/Test pairs)
- ☁️ Hybrid LLM approach: Cloud AI (Claude) for Architect, local models for other agents
- 💬 Chat-based interaction with real-time updates (SSE)
- 📋 Ticket-driven development with Kanban workflow
- 🔄 GitOps branching strategy (planned)
- 🧪 Strict TDD with Developer/Tester pairing (planned)
- 📊 Resource-aware model management with automatic eviction

## Quick Start

### Prerequisites
- Python 3.11+
- Poetry
- MongoDB (optional but recommended)
- ~5-10GB disk space for LLM models
- **Anthropic API key** (required for Architect agent - see [Cloud Setup Guide](docs/CLOUD_SETUP.md))
- **GPU (optional)**: NVIDIA GPU with CUDA support for faster inference. If no GPU is available, set `CPU_ONLY=true` in `.env` for testing purposes.

### Installation

1. **Clone and install dependencies:**
   ```bash
   cd C:\source\python\ATHBA
   poetry install
   ```

2. **Configure environment** (create `.env` file):
   ```env
   DJANGO_SECRET_KEY=your-secret-key
   DEBUG=True
   DJANGO_MONGO=mongodb://localhost:27017
   LLM_SERVER_URL=http://127.0.0.1:8011
   
   # REQUIRED: Anthropic API key for Architect agent
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   
   # Optional: Enable CPU-only mode for testing on systems without GPU
   CPU_ONLY=true
   ```
   
   See [Cloud Setup Guide](docs/CLOUD_SETUP.md) for detailed Anthropic configuration.

3. **Download models** to `llm_service/models/`:
   - `llama-3.2-3b-instruct-q4_k_m.gguf` (required for basic testing)
   - `codellama-7b-instruct.Q4_K_M.gguf` (required for developer/tester agents)
   - Additional models listed in [docs/SETUP.md](docs/SETUP.md)
   
   **Note**: For CPU-only testing, only the basic models above are needed. Set `CPU_ONLY=true` in your `.env` file to run without GPU acceleration. Claude will handle more complex tasks via the Anthropic API.

4. **Run migrations:**
   ```bash
   poetry run python manage.py migrate
   ```

### Running the Application

**Start two services:**

1. **LLM Server** (Terminal 1):
   ```bash
   poetry run uvicorn llm_service.llm_server:app --host 127.0.0.1 --port 8011 --reload
   ```

2. **Django App** (Terminal 2):
   ```bash
   poetry run uvicorn athba.asgi:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Access**: http://localhost:8000

## Usage Example

```
You: "Create a new project called Customer Portal"
PM: "I'll help you create a new project called 'Customer Portal'. 
     Routing you to the Spec Builder to gather requirements..."

Spec: "Great! Let's build the specification for Customer Portal.
       What is the main purpose of this application?"

You: "It's a web app where customers can view their orders and track shipments"
Spec: "Understood. I'll add that to the spec..."
```

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** - System design, agent architecture, data models
- **[Setup Guide](docs/SETUP.md)** - Detailed installation and configuration
- **[Usage Guide](docs/USAGE.md)** - How to use the system, chat commands, workflows
- **[Development Status](docs/STATUS.md)** - Current implementation state and roadmap
- **[API Reference](docs/API.md)** - REST API endpoints

## Current Status

### Implemented (Phase 1)
- Core agent system (PM, Spec Builder, Resource Director)
- LLM service with model registry and tiered models
- Chat UI with real-time streaming (SSE + HTMX)
- Project and ticket management
- MongoDB integration for persistent state
- Resource monitoring and model lifecycle management

### In Progress (Phase 2)
- Developer/Tester agent implementations
- GitOps workflow (clone, branch, commit, merge)
- TDD loop between Dev/Test pairs
- Kanban board UI

### Planned (Phase 3)
- Architect agent for code analysis and ticket generation
- Live specification editor
- Dashboard with project metrics
- Multi-project resource allocation
- Vector search for long-term memory

See [docs/STATUS.md](docs/STATUS.md) for detailed status and [DIVERGENCE.md](DIVERGENCE.md) for spec vs. implementation gaps.

## Project Structure

```
ATHBA/
├── athba/              # Django project settings
├── core/               # Main application
│   ├── agents/         # AI agent implementations
│   ├── dataclasses/    # Data models
│   ├── datastore/      # MongoDB repositories
│   ├── endpoints/      # API endpoints
│   ├── services/       # Business logic
│   └── sse/            # Server-Sent Events
├── llm_service/        # LLM server (FastAPI)
│   ├── models/         # GGUF model files
│   └── model_registry.py
├── templates/          # Django templates
├── static/             # CSS, JS assets
└── docs/               # Documentation
```

## Technology Stack

- **Backend**: Django <5.2, Django Ninja, FastAPI
- **Database**: SQLite + MongoDB (Motor)
- **LLM**: llama-cpp-python, quantized GGUF models
- **Frontend**: HTMX, Alpine.js, Tailwind CSS
- **Async**: Uvicorn (ASGI)

## Contributing

This is a personal research project. See [Specification Document.txt](Specification%20Document.txt) for the complete vision.

## License

Proprietary - Tom Pearce

## Author

Tom Pearce