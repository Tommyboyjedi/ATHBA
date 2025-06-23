from dataclasses import dataclass
from pathlib import Path

from llm_service.dataclasses.tier import Tiering
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier


BASE_DIR = Path(__file__).resolve().parent.parent

@dataclass
class AgentModelConfig:
    agent: EAgent
    models: Tiering
    n_ctx: Tiering
    n_threads: Tiering

    def get_path(self, tier: ETier) -> Path:
        tier_map = {
            ETier.STANDARD: self.models.standard,
            ETier.HEAVY: self.models.heavy,
            ETier.MEGA: self.models.mega
        }
        return BASE_DIR / tier_map[tier]

    def get_ctx(self, tier:ETier) -> int:
        tier_map = {
            ETier.STANDARD: self.n_ctx.standard,
            ETier.HEAVY: self.n_ctx.heavy,
            ETier.MEGA: self.n_ctx.mega
        }
        return int(tier_map[tier])

    def get_threads(self, tier: ETier) -> int:
        tier_map = {
            ETier.STANDARD: self.n_threads.standard,
            ETier.HEAVY: self.n_threads.heavy,
            ETier.MEGA: self.n_threads.mega
        }
        return int(tier_map[tier])


