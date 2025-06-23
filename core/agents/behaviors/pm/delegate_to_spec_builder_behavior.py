import asyncio
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.agents.spec_agent import SpecBuilderAgent

class DelegateToSpecBuilderBehavior(AgentBehavior):
    intent = {
        "start_spec",
        "edit_spec",
        "add_to_spec",
        "ask_a_question",
        "change_spec",
        "finalize_spec",
        "spec"
    }

    async def run(self, agent, content: str, intent) -> list[ChatMessage]:
        if intent.intent not in self.intent:
            return []

        # Launch SpecBuilderAgent asynchronously
        asyncio.create_task(self._run_spec_builder(agent.session, content))

        return [
            ChatMessage(
                sender=agent.name,
                content="📄 I've referred your request to the Specification Builder agent for this project."
            )
        ]

    async def _run_spec_builder(self, session, user_input: str):
        spec_agent = SpecBuilderAgent(session=session.clone())
        await spec_agent.initialize()
        await spec_agent.run(user_input)
