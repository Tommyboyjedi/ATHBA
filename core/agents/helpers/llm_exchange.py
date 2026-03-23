
import json
import re
import os
import requests

from core.agents.helpers.llm_response_parser import LlmResponseParser
from llm_service.py_models.llm_request import LLMRequest
from core.dataclasses.llm_intent import LlmIntent
from llm_service.enums.etier import ETier

class LlmExchange:
    def __init__(self, agent, session, content: str, tier: ETier = ETier.STANDARD, use_cloud: bool = False):
        self.agent = agent
        self.session = session
        self.content = content
        self.tier = tier
        self.use_cloud = use_cloud

    async def get_intent(self) -> LlmIntent:
        """Get intent from LLM with optional cloud provider support."""
        
        # If cloud is requested, use Anthropic provider
        if self.use_cloud:
            return await self._get_intent_from_cloud()
        
        # Otherwise use local LLM server
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

    async def _get_intent_from_cloud(self) -> LlmIntent:
        """Get intent using cloud provider (Anthropic Claude)."""
        try:
            from core.llm.providers.anthropic_provider import AnthropicProvider
            
            provider = AnthropicProvider()
            prompt = self.agent.llm_prompt + self.content
            
            print(f"[CLOUD] PROMPT SENT TO CLAUDE: {prompt[:200]}...")
            
            result = provider.invoke(
                prompt=prompt,
                model="claude-sonnet-4.5-20250514",
                temperature=0.0,
                max_tokens=1024
            )
            
            raw = result.text
            print(f"[CLOUD] CLAUDE RESPONSE: {raw[:200]}...")
            
            if not raw or raw == "[]":
                return LlmIntent(response="cloud llm returned empty", intent="error", agents_routing=[], entities={})

            parsed_list = LlmResponseParser.parse(raw)
            if parsed_list:
                parsed = parsed_list[0]
            else:
                return LlmIntent(response="cloud llm return didnt parse", intent="error", agents_routing=[], entities={})

            intent = LlmIntent(
                response=parsed.get("response", ""),
                intent=parsed.get("intent", ""),
                agents_routing=parsed.get("agents_routing", []),
                entities=parsed.get("entities", {})
            )
            return intent
            
        except Exception as e:
            print(f"[CLOUD] ERROR: {e}")
            return LlmIntent(response=f"❌ Error talking to cloud LLM: {e}", intent="error", agents_routing=[], entities={})

    async def get_response(self) -> str:
        """Get a raw text response from LLM without intent parsing."""
        
        # If cloud is requested, use Anthropic provider
        if self.use_cloud:
            return await self._get_response_from_cloud()
        
        # Otherwise use local LLM server
        llm_request = LLMRequest(
            agent=self.agent.agent_type,
            tier=self.tier,
            project_id=self.session.project_id,
            prompt=self.content  # Just the content, not the agent prompt
        )

        try:
            response = requests.post(
                f"{os.environ.get('LLM_SERVER_URL', 'http://localhost:8011')}/llm/infer",
                json=llm_request.model_dump(),
                timeout=120  # Longer timeout for spec analysis
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except Exception as e:
            return f"Error: {e}"

    async def _get_response_from_cloud(self) -> str:
        """Get raw response using cloud provider (Anthropic Claude)."""
        try:
            from core.llm.providers.anthropic_provider import AnthropicProvider
            
            provider = AnthropicProvider()
            
            print(f"[CLOUD] PROMPT SENT TO CLAUDE: {self.content[:200]}...")
            
            result = provider.invoke(
                prompt=self.content,
                model="claude-sonnet-4.5-20250514",
                temperature=0.0,
                max_tokens=4096  # More tokens for spec analysis
            )
            
            print(f"[CLOUD] CLAUDE RESPONSE: {result.text[:200]}...")
            print(f"[CLOUD] USAGE: {result.usage}")
            
            return result.text
            
        except Exception as e:
            print(f"[CLOUD] ERROR: {e}")
            return f"Error: {e}"


