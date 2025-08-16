from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.services.spec_service import SpecService

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

        await SpecService().append_content(agent.session.project_id, html_block, author=agent.name)

        return [ChatMessage(
            sender=agent.name,
            content=f"📌 I've added your input to the spec under: _{section_title}_."
        )]
