from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.questions_service import QuestionsService
from core.services.spec_service import SpecService


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

        # If the LLM provided some structure, append distilled content to the spec as progress
        try:
            entities = llm_response.entities or {}
            sections = entities.get("specSections") or []
            ideas = entities.get("humanIdeas") or []
            if sections or ideas:
                section_title = sections[0] if sections else "Overview"
                body = "; ".join(ideas) if ideas else user_input
                html_block = f"<h2>{section_title}</h2>\n<p>{body}</p>"
                await SpecService().append_content(agent.session.project_id, html_block, author=agent.name)
        except Exception:
            # Non-fatal: continue even if we can't append right now
            pass

        # Ask the clarifying question back to the user as a chat message
        return ChatMessage(
            sender=agent.name,
            content=llm_response.response,
            metadata={"open_spec_panel": True},
        )
