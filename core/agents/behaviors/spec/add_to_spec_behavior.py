from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.services.spec_service import SpecService
from core.services.questions_service import QuestionsService

class AddToSpecBehavior(AgentBehavior):
    async def run(self, agent, content: str, intent) -> list[ChatMessage]:
        if intent.intent != "add_to_spec":
            return []

        # Build a simple HTML block from entities or fallback to the LLM response
        entities = intent.entities or {}
        sections = entities.get("specSections") or []
        ideas = entities.get("humanIdeas") or []
        section_title = sections[0] if sections else "New Requirement"
        body = intent.response or content
        if ideas:
            body = "; ".join(ideas)
        html_block = f"<h2>{section_title}</h2>\n<p>{body}</p>"

        spec_service = SpecService()
        await spec_service.append_content(agent.session.project_id, html_block, author=agent.name)
        # Best-effort: close the latest open question with user's reply and link to spec version
        latest_version = await spec_service.get_latest_version(agent.session.project_id)
        await QuestionsService().answer_latest_open(
            project_id=agent.session.project_id,
            session_id=agent.session.session_id,
            answer_text=content,
            linked_spec_version=latest_version,
        )

        return [ChatMessage(
            sender=agent.name,
            content=f"📌 I've added your input to the spec under: _{section_title}_."
        )]
