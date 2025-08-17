from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.services.spec_service import SpecService


class StartSpecBehavior(AgentBehavior):
    intent = ['start_spec', 'begin_spec', 'commence_spec', 'initiate_spec', 'launch_spec', 'start', 'begin', 'commence',
              'initiate', 'launch']

    async def run(self, agent, content: str, intent) -> list[ChatMessage]:
        if intent.intent not in self.intent:
            return []

        # Initialize a new spec document if one does not exist
        svc = SpecService()
        exists = await svc.spec_exists(agent.session.project_id)
        if not exists:
            await svc.initialize_spec(agent.session.project_id, author=agent.name)

        return [
            ChatMessage(
                sender=agent.name,
                content="🧱 I've created the initial structure for the project specification. Please describe your first requirement.",
                metadata={"open_spec_panel": True}
            )
        ]

