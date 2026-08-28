from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage


class StartSpecBehavior(AgentBehavior):
    intent = [
        "start_spec",
        "begin_spec",
        "commence_spec",
        "initiate_spec",
        "launch_spec",
        "start",
        "begin",
        "commence",
        "initiate",
        "launch",
    ]

    async def run(self, agent, content: str, intent) -> list[ChatMessage] | None:
        if intent.intent not in self.intent:
            return None

        return [
            ChatMessage(
                sender=agent.name,
                content="🧱 I've created the initial structure for the project specification. Please describe your first requirement.",
            )
        ]
