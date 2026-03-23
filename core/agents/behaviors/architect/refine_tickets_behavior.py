from core.agents.interfaces import AgentBehavior
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent


class RefineTicketsBehavior(AgentBehavior):
    intent = ["refine_tickets"]

    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return None

        # Get existing tickets for this project
        tickets = await agent.ticket_repo.list_all(agent.session.project_id)
        
        if not tickets:
            return AgentMessage(
                sender=agent.name,
                text="❌ No tickets found to refine. Please generate tickets first by analyzing the specification."
            )

        return AgentMessage(
            sender=agent.name,
            text=f"✅ I found {len(tickets)} existing tickets. Ticket refinement is coming soon. For now, please use the Kanban board to manually edit tickets."
        )
