from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage

class AddToSpecBehavior(AgentBehavior):
    async def run(self, agent, content: str, intent) -> list[ChatMessage]:
        if intent.intent != "add_to_spec":
            return []

        return [ChatMessage(
            sender=agent.name,
            content="📌 I've added your new requirement to the spec section: _User Authentication_."
        )]
