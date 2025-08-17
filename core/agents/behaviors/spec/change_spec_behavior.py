from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.questions_service import QuestionsService


class ChangeSpecBehavior(AgentBehavior):
    intent = ["change_spec"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> ChatMessage | None:
        if llm_response.intent not in self.intent:
            return None

        # Best-effort: mark latest open question as answered with user's input
        await QuestionsService().answer_latest_open(
            project_id=agent.session.project_id,
            session_id=agent.session.session_id,
            answer_text=user_input,
            linked_spec_version=None,
        )

        return ChatMessage(
            sender=agent.name,
            content="✅ This is a stub for ChangeSpecBehavior responding to intent 'change_spec'."
        )
