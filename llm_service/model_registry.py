import os
from pathlib import Path
from typing import Dict
from dotenv import load_dotenv

# 1. Load environment
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


from llm_service.dataclasses.agent_model_config import AgentModelConfig
from llm_service.dataclasses.tier import Tiering
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier

BASE_DIR = Path(__file__).resolve().parent

FLOW_JUDGE_PATH = BASE_DIR / "models" / "Flow-Judge-v0.1.Q4_K_M.gguf"
FLOW_JUDGE_ENABLED = os.getenv("ENABLE_FLOW_JUDGE", "true").lower() == "true"


class ModelRegistry:
    def __init__(self):
        self.registry: Dict[EAgent, AgentModelConfig] = {
            EAgent.PM: AgentModelConfig(
                agent=EAgent.PM,
                models=Tiering(
                    standard="./models/llama-3.2-3b-instruct-q4_k_m.gguf",
                    heavy="./models/Yi-1.5-9B-Chat-Q4_K_M.gguf",
                    mega="./models/dolphin-llama-13b.Q4_K_M.gguf"
                ),
                n_ctx=Tiering(
                    standard=2048,
                    heavy=2048,
                    mega=4096
                ),
                n_threads=Tiering(
                    standard=8,
                    heavy=8,
                    mega=10
                )
            ),
            EAgent.Developer: AgentModelConfig(
                agent=EAgent.Developer,
                models=Tiering(
                    standard="./models/codellama-7b-instruct.Q4_K_M.gguf",
                    heavy="./models/starcoder2-15b-instruct-Q4_K_M.gguf",
                    mega="./models/starcoder2-15b-instruct-Q4_K_M.gguf"
            ),
                n_ctx=Tiering(
                    standard=2048,
                    heavy=2048,
                    mega=4096
                ),
                n_threads=Tiering(
                    standard=8,
                    heavy=8,
                    mega=10
                )
            ),
            EAgent.Architect: AgentModelConfig(
                agent=EAgent.Architect,
                models=Tiering(
                    standard="./models/llama-3.2-3b-instruct-q4_k_m.gguf",
                    heavy="./models/Yi-1.5-9B-Chat-Q4_K_M.gguf",
                    mega="./models/dolphin-llama-13b.Q4_K_M.gguf"
                ),
                n_ctx=Tiering(
                    standard=2048,
                    heavy=2048,
                    mega=4096
                ),
                n_threads=Tiering(
                    standard=8,
                    heavy=8,
                    mega=10
                )
            ),
            EAgent.Tester: AgentModelConfig(
                agent=EAgent.Tester,
                models=Tiering(
                    standard="./models/codellama-7b-instruct.Q4_K_M.gguf",
                    heavy="./models/starcoder2-15b-instruct-Q4_K_M.gguf",
                    mega="./models/starcoder2-15b-instruct-Q4_K_M.gguf"
                ),
                n_ctx=Tiering(
                    standard=2048,
                    heavy=2048,
                    mega=4096
                ),
                n_threads=Tiering(
                    standard=8,
                    heavy=8,
                    mega=10
                )
            ),
            EAgent.RD: AgentModelConfig(
                agent=EAgent.RD,
                models=Tiering(
                    standard="./models/llama-3.2-3b-instruct-q4_k_m.gguf",
                    heavy="./models/Yi-1.5-9B-Chat-Q4_K_M.gguf",
                    mega="./models/dolphin-llama-13b.Q4_K_M.gguf"
                ),
                n_ctx=Tiering(
                    standard=2048,
                    heavy=2048,
                    mega=4096
                ),
                n_threads=Tiering(
                    standard=8,
                    heavy=8,
                    mega=10
                )
            ),
            EAgent.Spec: AgentModelConfig(
                agent=EAgent.Spec,
                models=Tiering(
                    standard="./models/llama-3.2-3b-instruct-q4_k_m.gguf",
                    heavy="./models/Yi-1.5-9B-Chat-Q4_K_M.gguf",
                    mega="./models/dolphin-llama-13b.Q4_K_M.gguf"
                ),
                n_ctx=Tiering(
                    standard=4096,
                    heavy=4096,
                    mega=4096
                ),
                n_threads=Tiering(
                    standard=8,
                    heavy=8,
                    mega=10
                )
            )
        }

    def get_model(self, agent: EAgent, tier: ETier) -> Path:
        if agent not in self.registry:
            raise ValueError(f"Unknown agent: {agent}")
        return self.registry[agent].get_path(tier)

    def get_ctx(self, agent: EAgent, tier: ETier) -> Path:
        if agent not in self.registry:
            raise ValueError(f"Unknown agent: {agent}")
        return self.registry[agent].get_ctx(tier)

    def get_threads(self, agent: EAgent, tier: ETier) -> Path:
        if agent not in self.registry:
            raise ValueError(f"Unknown agent: {agent}")
        return self.registry[agent].get_threads(tier)
