from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage


class BasicReplyBehavior(AgentBehavior):
    intent = ["basic_reply"]

    async def run(self, agent, content: str, llm_response) -> list[ChatMessage]:
        if llm_response.intent in self.intent:
            # Always returns the raw LLM response if no other behavior has matched
            return [
                ChatMessage(
                    sender=agent.name,
                    content=llm_response.response.strip()
                )
            ]
        return []
