# llm_server_state.py
import os
from llm_service.model_registry import ModelRegistry
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier

# Runtime config
mem_threshold = float(os.getenv("RD_MEM_THRESHOLD", "90.0"))
cpu_threshold = float(os.getenv("RD_CPU_THRESHOLD", "95.0"))
check_interval = int(os.getenv("LLM_STATUS_INTERVAL", "10"))
model_idle_ttl = int(os.getenv("LLM_MODEL_TTL", "120"))

# Model runtime state
loaded_models = {}
model_locks = {}
model_last_used = {}

# Registry (optional singleton)
registry = ModelRegistry()
