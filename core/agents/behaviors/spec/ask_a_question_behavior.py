from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.questions_service import QuestionsService


class AskAQuestionBehavior(AgentBehavior):
    intent = ["ask_a_question", "query", "ask", "inquire", "question", "interrogate", "probe", "request_info"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> ChatMessage | None:
        if llm_response.intent not in self.intent:
            return None

        # Persist the asked question as an open question for this project/session
        await QuestionsService().ask_question(
            project_id=agent.session.project_id,
            session_id=agent.session.session_id,
            question_text=llm_response.response,
            asked_by=agent.name,
        )

        # Ask the clarifying question back to the user as a chat message
        return ChatMessage(
            sender=agent.name,
            content=llm_response.response,
        )
