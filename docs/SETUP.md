# ATHBA Setup Guide

## System Requirements

### Hardware
- **RAM**: Minimum 8GB, 16GB+ recommended
- **Storage**: 10-15GB for models and project data
- **CPU**: Multi-core processor (8+ threads recommended)
- **GPU**: Optional but recommended
  - NVIDIA GPU with CUDA support for faster inference
  - For systems without GPU, enable CPU-only mode (see Configuration section)

### Software
- **OS**: Windows 10/11, Linux, or macOS
- **Python**: 3.11 or higher
- **Poetry**: Latest version
- **MongoDB**: 5.0+ (optional but recommended)

## Installation

### 1. Clone the Repository

```bash
cd C:\source\python
git clone <repository-url> ATHBA
cd ATHBA
```

### 2. Install Dependencies

```bash
poetry install
```

This installs all dependencies from `pyproject.toml`:
- Django <5.2
- django-ninja
- pymongo, motor
- llama-cpp-python
- fastapi, uvicorn
- psutil, autoevals
- And more...

### 3. Download LLM Models

Create the models directory:
```bash
mkdir llm_service\models
```

Download these quantized GGUF models and place in `llm_service/models/`:

#### Required Models
- **llama-3.2-3b-instruct-q4_k_m.gguf** (~2GB)
  - Used by: PM Agent, Spec Builder
  - Source: Hugging Face (search for "llama-3.2-3b GGUF")
  
- **codellama-7b-instruct.Q4_K_M.gguf** (~4GB)
  - Used by: Developer/Tester agents
  - Source: Hugging Face (search for "codellama-7b GGUF")

#### Optional Models (for heavy tasks)
- **Yi-1.5-9B-Chat-Q4_K_M.gguf** (~5GB)
  - Heavy tier for PM/Architect
  
- **dolphin-llama-13b.Q4_K_M.gguf** (~7GB)
  - Mega tier for complex reasoning
  
- **starcoder2-15b-instruct-Q4_K_M.gguf** (~8GB)
  - Heavy tier for Developer/Tester

- **Flow-Judge-v0.1.Q4_K_M.gguf** (~2GB)
  - Quality evaluation model

### 4. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Django Configuration
DJANGO_SECRET_KEY=your-secret-key-here-change-this
DEBUG=True

# Database
DJANGO_MONGO=mongodb://localhost:27017

# LLM Service
LLM_SERVER_URL=http://127.0.0.1:8011
LLM_MODEL_TTL=120
ENABLE_FLOW_JUDGE=false

# CPU-only mode (set to true to disable GPU acceleration)
# Useful for testing on systems without dedicated GPU
# When enabled, only basic models run on CPU and Claude is used for complex tasks
CPU_ONLY=false

# DevOps Directory (where Git repos will be cloned)
DEVOPS_DIR=c:\devops
```

**Generate a secret key:**
```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### CPU-Only Mode (For Testing Without GPU)

If you're running on a high-performance PC without a dedicated GPU, or just want to test the application functionality without worrying about GPU setup, enable CPU-only mode:

1. **Set the environment variable in `.env`:**
   ```env
   CPU_ONLY=true
   ```

2. **What CPU-only mode does:**
   - Disables GPU acceleration for local LLM models (sets `n_gpu_layers=0` in llama-cpp-python)
   - Local models run entirely on CPU (slower but works on any system)
   - Claude (Anthropic API) is still used for complex tasks via the Architect agent
   - Perfect for testing application logic and workflows without GPU requirements

3. **Performance considerations:**
   - CPU inference will be slower than GPU (10-60 seconds per response vs 2-5 seconds)
   - Only download the required basic models (llama-3.2-3b, codellama-7b)
   - The application remains fully functional for testing purposes
   - Response quality from local models may vary; Claude handles complex tasks

4. **Recommended for:**
   - Testing application functionality without GPU
   - Development and debugging workflows
   - Verifying integrations and agent behavior
   - Systems with powerful CPUs but no dedicated GPU

**Note:** This mode is explicitly designed for testing. For production use with quality LLM responses, a GPU or relying more heavily on Claude API is recommended.

### 5. Setup MongoDB (Optional)

If using MongoDB for persistent agent data:

**Windows:**
```bash
# Install MongoDB Community Edition
# Download from: https://www.mongodb.com/try/download/community

# Start MongoDB service
net start MongoDB

# Or run manually:
mongod --dbpath C:\data\db
```

**Linux/macOS:**
```bash
# Install via package manager
sudo apt-get install mongodb  # Ubuntu/Debian
brew install mongodb-community  # macOS

# Start service
sudo systemctl start mongod  # Linux
brew services start mongodb-community  # macOS
```

**Without MongoDB:**
The system will still work using SQLite only, but agent data persistence will be limited.

### 6. Run Django Migrations

```bash
poetry run python manage.py migrate
```

This creates the SQLite database with Django's default tables.

### 7. Create DevOps Directory

Create the directory where Git repositories will be cloned:

```bash
mkdir c:\devops  # Windows
mkdir ~/devops   # Linux/macOS
```

## Running the Application

The application requires **two separate services** to run simultaneously.

### Service 1: LLM Server (Port 8011)

**Terminal/Command Prompt 1:**
```bash
cd C:\source\python\ATHBA
poetry run uvicorn llm_service.llm_server:app --host 127.0.0.1 --port 8011 --reload
```

Or use the batch file (Windows):
```bash
"run scripts\llm_service_run.bat"
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8011
[BOOT] Preloading PM standard model: ./models/llama-3.2-3b-instruct-q4_k_m.gguf
[RD] Watchdog started
```

### Service 2: Django Application (Port 8000)

**Terminal/Command Prompt 2:**
```bash
cd C:\source\python\ATHBA
poetry run uvicorn athba.asgi:app --host 0.0.0.0 --port 8000 --reload
```

Or use the batch file (Windows):
```bash
"run scripts\commercial_agentic_ai.bat"
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Access the Application

Open your browser to:
```
http://localhost:8000
```

## Verifying the Installation

### 1. Check LLM Server Status

```bash
curl http://127.0.0.1:8011/llm/status
```

Expected response:
```json
[
  {
    "model": "./models/llama-3.2-3b-instruct-q4_k_m.gguf",
    "last_used": 1234567890.123,
    "idle_time": 5.2
  }
]
```

### 2. Test Chat Interface

1. Navigate to http://localhost:8000
2. Type: "Hello"
3. PM Agent should respond within a few seconds

### 3. Create a Test Project

1. In chat, type: "Create a new project called Test Project"
2. PM should confirm project creation
3. Spec Builder should engage for requirements

## Troubleshooting

### LLM Server Won't Start

**Error: Model file not found**
```
Solution: Ensure GGUF files are in llm_service/models/ directory
Check paths in llm_service/model_registry.py match your files
```

**Error: Port 8011 already in use**
```
Solution: Kill existing process or change port in .env:
LLM_SERVER_URL=http://127.0.0.1:8012
```

### Django App Won't Start

**Error: SECRET_KEY not set**
```
Solution: Add DJANGO_SECRET_KEY to .env file
```

**Error: MongoDB connection failed**
```
Solution: 
1. Start MongoDB service
2. Or comment out DJANGO_MONGO in .env to skip MongoDB
```

### Models Loading Slowly

**Issue: First request takes 30+ seconds**
```
Reason: Model needs to load into RAM
Solution: This is normal. Subsequent requests will be fast.
Enable model preloading in llm_server.py for frequently used models.
```

### High Memory Usage

**Issue: System using 10+ GB RAM**
```
Reason: Multiple large models loaded
Solution: 
1. Lower LLM_MODEL_TTL to unload models faster
2. Use smaller models (standard tier only)
3. Enable ENABLE_FLOW_JUDGE=false
```

### Chat Not Responding

**Check these:**
1. Both services running (LLM server + Django app)
2. LLM server accessible at http://127.0.0.1:8011/llm/status
3. Check browser console for errors (F12)
4. Check terminal output for Python errors

## Development Setup

### Enable Debug Mode

In `.env`:
```env
DEBUG=True
```

This enables:
- Detailed error pages
- Static file serving without collectstatic
- Auto-reload on code changes

### Install Development Tools

```bash
# Optional: Install development dependencies
poetry add --group dev pytest black flake8 mypy
```

### Database Inspection

**MongoDB:**
```bash
mongosh
use athba
db.projects.find()
db.tickets.find()
```

**SQLite:**
```bash
poetry run python manage.py dbshell
.tables
SELECT * FROM django_session;
```

## Production Deployment (Future)

**Not yet production-ready.** Current implementation is for development/research only.

For future production deployment, consider:
- Set `DEBUG=False`
- Use PostgreSQL instead of SQLite
- Configure proper MongoDB authentication
- Use nginx/Apache as reverse proxy
- Set up systemd services (Linux) or Windows Services
- Configure SSL/TLS certificates
- Implement rate limiting and authentication
- Use gunicorn or similar production ASGI server

## Next Steps

After successful installation:
1. Read [docs/USAGE.md](USAGE.md) for usage instructions
2. Review [docs/ARCHITECTURE.md](ARCHITECTURE.md) for system understanding
3. Check [docs/STATUS.md](STATUS.md) for current capabilities
