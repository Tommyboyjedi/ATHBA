from dataclasses import dataclass
from typing import Optional

from core.dataclasses.llm_evaluation import LlmEvaluation


@dataclass
class LlmIntent:
    response: str
    intent: str
    agents_routing: list
    entities: dict
    evaluation: Optional[LlmEvaluation] = None



