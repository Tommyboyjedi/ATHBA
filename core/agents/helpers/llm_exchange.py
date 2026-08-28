import os

import requests

from core.agents.helpers.llm_response_parser import LlmResponseParser
from core.dataclasses.llm_intent import LlmIntent
from core.llm.providers.anthropic_provider import AnthropicProvider
from llm_service.enums.etier import ETier
from llm_service.py_models.llm_request import LLMRequest


class LlmExchange:
    def __init__(self, agent, session, content: str, tier: ETier = ETier.STANDARD, use_cloud: bool = False):
        self.agent = agent
        self.session = session
        self.content = content
        self.tier = tier
        self.use_cloud = use_cloud

    async def get_intent(self) -> LlmIntent:
        if self.use_cloud:
            return await self._get_intent_from_cloud()

        llm_request = LLMRequest(
            agent=self.agent.agent_type,
            tier=self.tier,
            project_id=self.session.project_id,
            prompt=self.agent.llm_prompt + self.content,
        )

        try:
            response = requests.post(
                f"{os.environ.get('LLM_SERVER_URL', 'http://localhost:8011')}/llm/infer",
                json=llm_request.model_dump(),
                timeout=60,
            )
            response.raise_for_status()
            raw = response.json().get("response", "")
            return self._parse_intent_response(raw, "local")
        except Exception as exc:
            return LlmIntent(
                response=f"Error talking to LLM: {exc}",
                intent="error",
                agents_routing=[],
                entities={},
            )

    async def _get_intent_from_cloud(self) -> LlmIntent:
        try:
            provider = AnthropicProvider()
            prompt = self.agent.llm_prompt + self.content
            result = provider.invoke(
                prompt=prompt,
                model="claude-sonnet-4.5-20250514",
                temperature=0.0,
                max_tokens=1024,
            )
            return self._parse_intent_response(result.text, "cloud")
        except Exception as exc:
            return LlmIntent(
                response=f"Error talking to cloud LLM: {exc}",
                intent="error",
                agents_routing=[],
                entities={},
            )

    def _parse_intent_response(self, raw: str, source: str) -> LlmIntent:
        if not raw or raw == "[]":
            return LlmIntent(
                response=f"{source} llm returned empty",
                intent="error",
                agents_routing=[],
                entities={},
            )

        parsed_list = LlmResponseParser.parse(raw)
        if not parsed_list:
            return LlmIntent(
                response=f"{source} llm return didnt parse",
                intent="error",
                agents_routing=[],
                entities={},
            )

        parsed = parsed_list[0]
        return LlmIntent(
            response=parsed.get("response", ""),
            intent=parsed.get("intent", ""),
            agents_routing=parsed.get("agents_routing", []),
            entities=parsed.get("entities", {}),
        )

    async def get_response(self) -> str:
        if self.use_cloud:
            return await self._get_response_from_cloud()

        llm_request = LLMRequest(
            agent=self.agent.agent_type,
            tier=self.tier,
            project_id=self.session.project_id,
            prompt=self.content,
        )

        try:
            response = requests.post(
                f"{os.environ.get('LLM_SERVER_URL', 'http://localhost:8011')}/llm/infer",
                json=llm_request.model_dump(),
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as exc:
            return f"Error: {exc}"

    async def _get_response_from_cloud(self) -> str:
        try:
            provider = AnthropicProvider()
            result = provider.invoke(
                prompt=self.content,
                model="claude-sonnet-4.5-20250514",
                temperature=0.0,
                max_tokens=4096,
            )
            return result.text
        except Exception as exc:
            return f"Error: {exc}"
