
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

    async def get_intents(self) -> list[LlmIntent]:
        prompt = self.agent.llm_prompt + self.content
        return await self.infer_with_prompt(prompt)

    async def infer_with_prompt(self, prompt: str) -> list[LlmIntent]:
        llm_request = LLMRequest(
            agent=self.agent.agent_type,
            tier=self.tier,
            prompt=prompt
        )

        print("PROMPT SENT TO LLM:", prompt)
        try:
            response = requests.post(
                f"{os.environ.get('LLM_SERVER_URL', 'http://localhost:8011')}/llm/infer",
                json=llm_request.model_dump(),
                timeout=60
            )
            response.raise_for_status()

            raw = response.json().get("response", "")

            if not raw or raw.strip() == "[]":
                return []

            parsed_list = LlmResponseParser.parse(raw)
            intents: list[LlmIntent] = []
            for item in (parsed_list or []):
                intents.append(LlmIntent(
                    response=item.get("response", ""),
                    intent=item.get("intent", ""),
                    agents_routing=item.get("agents_routing", []),
                    entities=item.get("entities", {})
                ))
            return intents

        except Exception as e:
            print(f"❌ Error talking to LLM: {e}")
            return []

    async def get_intent(self) -> LlmIntent:
        """Backward-compatible single-intent accessor (returns first item or an error-intent)."""
        intents = await self.get_intents()
        if intents:
            return intents[0]
        return LlmIntent(response="raw llm returned empty or could not be parsed", intent="error", agents_routing=[], entities={})


