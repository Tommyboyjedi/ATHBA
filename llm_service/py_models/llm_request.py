from pydantic import BaseModel

from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier


class LLMRequest(BaseModel):
    agent: EAgent
    tier: ETier
    prompt: str
    max_tokens: int = 256
    evaluate: bool = True

