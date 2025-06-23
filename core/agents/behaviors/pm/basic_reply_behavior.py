from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage


class BasicReplyBehavior(AgentBehavior):
    async def run(self, agent, content: str, intent) -> list[ChatMessage]:
        # Always returns the raw LLM response if no other behavior has matched
        return [
            ChatMessage(
                sender=agent.name,
                content=intent.response.strip()
            )
        ]
