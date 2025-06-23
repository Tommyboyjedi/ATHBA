
import json
import re
import os
import requests

from core.agents.helpers.llm_response_parser import LlmResponseParser
from llm_service.py_models.llm_request import LLMRequest
from core.dataclasses.llm_intent import LlmIntent
from llm_service.enums.etier import ETier

class LlmExchange:
    def __init__(self, agent, session, content: str, tier: ETier = ETier.STANDARD):
        self.agent = agent
        self.session = session
        self.content = content
        self.tier = tier

    async def get_intent(self) -> LlmIntent:
        llm_request = LLMRequest(
            agent=self.agent.agent_type,
            tier=self.tier,
            project_id=self.session.project_id,
            prompt=self.agent.llm_prompt + self.content
        )

        print("PROMPT SENT TO LLM:", self.agent.llm_prompt + self.content)
        try:
            response = requests.post(
                f"{os.environ.get('LLM_SERVER_URL', 'http://localhost:8011')}/llm/infer",
                json=llm_request.model_dump(),
                timeout=60
            )
            response.raise_for_status()

            raw = response.json().get("response", "")

            if raw == "[]":
                return LlmIntent(response="raw llm returned empty",intent="error",agents_routing=[],entities={})

            parsed_list = LlmResponseParser.parse(raw)
            if parsed_list:
                parsed = parsed_list[0]
            else:
                return LlmIntent(response="raw llm return didnt parse",intent="error",agents_routing=[],entities={})

            intent = LlmIntent(
                response=parsed.get("response", ""),
                intent=parsed.get("intent", ""),
                agents_routing=parsed.get("agents_routing", []),
                entities=parsed.get("entities", {})
            )
            return intent

        except Exception as e:
            return LlmIntent(response=f"❌ Error talking to LLM: {e}", intent="error", agents_routing=[],entities={})


