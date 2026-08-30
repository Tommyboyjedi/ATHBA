from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class RefineTicketsBehavior:
    intent = ["refine_tickets"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent not in self.intent:
            return None

        # Get existing tickets for this project
        tickets = await agent.ticket_repo.list_all(agent.session.project_id)
        
        if not tickets:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No tickets found to refine. Please generate tickets first by analyzing the specification."
            )]

        return [ChatMessage(
            sender=agent.name,
            content=f"✅ I found {len(tickets)} existing tickets. Ticket refinement is coming soon. For now, please use the Kanban board to manually edit tickets."
        )]

