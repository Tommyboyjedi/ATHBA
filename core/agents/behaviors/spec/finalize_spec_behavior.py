from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.spec_service import SpecService


class FinalizeSpecBehavior(AgentBehavior):
    intent = ["finalize_spec"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> ChatMessage | None:
        if llm_response.intent not in self.intent:
            return None

        await SpecService().finalize_spec(agent.session.project_id, author=agent.name)
        return ChatMessage(
            sender=agent.name,
            content="✅ Specification finalized. Ready for Architect to generate design and tickets."
        )
