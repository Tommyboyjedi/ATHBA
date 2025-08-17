from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.questions_service import QuestionsService
from core.services.spec_service import SpecService


class ChangeSpecBehavior(AgentBehavior):
    intent = ["change_spec"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> ChatMessage | None:
        if llm_response.intent not in self.intent:
            return None

        # Append change details to the spec
        section_title = "Change Request"
        body = llm_response.response or user_input
        html_block = f"<h2>{section_title}</h2>\n<p>{body}</p>"

        svc = SpecService()
        await svc.append_content(agent.session.project_id, html_block, author=agent.name)
        latest_version = await svc.get_latest_version(agent.session.project_id)

        # Best-effort: mark latest open question as answered with user's input and link to spec version
        await QuestionsService().answer_latest_open(
            project_id=agent.session.project_id,
            session_id=agent.session.session_id,
            answer_text=user_input,
            linked_spec_version=latest_version,
        )

        return ChatMessage(
            sender=agent.name,
            content="✅ I've updated the spec based on your change.",
            metadata={"open_spec_panel": True}
        )
