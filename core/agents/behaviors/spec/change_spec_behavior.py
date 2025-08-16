from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class ChangeSpecBehavior(AgentBehavior):
    intent = ["change_spec"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> ChatMessage | None:
        if llm_response.intent not in self.intent:
            return None

        return ChatMessage(
            sender=agent.name,
            content="✅ This is a stub for ChangeSpecBehavior responding to intent 'change_spec'."
        )
