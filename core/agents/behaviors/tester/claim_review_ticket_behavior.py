"""
Claim Review Ticket Behavior for Tester Agent.

This behavior allows the Tester agent to claim tickets from the Review column.
"""

from datetime import datetime
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.history_entry import HistoryEntry


class ClaimReviewTicketBehavior(AgentBehavior):
    """
    Behavior for claiming a ticket from the Review column.
    
    When triggered, this behavior:
    1. Finds available tickets in the Review column
    2. Claims a specific ticket or the highest priority one
    3. Assigns the Tester agent to the ticket
    4. Updates ticket history
    5. Stores ticket reference in session
    """
    
    intent = ["claim_review", "claim_ticket", "review_ticket"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the claim review ticket behavior.
        
        Args:
            agent: Tester agent instance
            user_input: User's input message
            llm_response: LLM intent detection response
            
        Returns:
            List of ChatMessage responses, or None if not applicable
        """
        if llm_response.intent not in self.intent:
            return None
        
        # Get ticket ID from entities if provided
        ticket_id = None
        if llm_response.entities and "ticketId" in llm_response.entities:
            ticket_id = llm_response.entities["ticketId"]
        
        # If specific ticket requested, get it
        if ticket_id:
            ticket = await agent.ticket_repo.get_ticket_by_id(ticket_id)
            if not ticket:
                return [ChatMessage(
                    sender=agent.name,
                    content=f"❌ Ticket {ticket_id} not found."
                )]
            
            if ticket.column != "Review":
                return [ChatMessage(
                    sender=agent.name,
                    content=f"❌ Ticket '{ticket.title}' is not in Review (currently in {ticket.column})."
                )]
        else:
            # Get all tickets in Review column
            tickets = await agent.ticket_repo.get_tickets_by_column(
                agent.project.id, 
                "Review"
            )
            
            if not tickets:
                return [ChatMessage(
                    sender=agent.name,
                    content="📋 No tickets available in the Review column."
                )]
            
            # Priority order: Critical > High > Medium > Low
            priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            tickets.sort(key=lambda t: priority_order.get(t.severity, 99))
            
            # Get the highest priority ticket
            ticket = tickets[0]
        
        # Assign Tester to ticket
        if "Tester" not in ticket.agents:
            ticket.agents.append("Tester")
        
        # Add history entry
        ticket.history.append(HistoryEntry(
            timestamp=datetime.utcnow(),
            agent="Tester",
            action="claim_review",
            details=f"Tester claimed ticket for review from {ticket.column} column"
        ))
        
        ticket.updated_at = datetime.utcnow()
        
        # Save ticket
        await agent.ticket_repo.update(ticket)
        
        # Store ticket reference in session
        agent.session.current_ticket = ticket.id
        
        # Format response
        response_msg = f"""✅ **Claimed Ticket for Review**

**Ticket:** {ticket.title}
**ID:** {ticket.id}
**Severity:** {ticket.severity}
**Branch:** {ticket.branch_name or 'None'}
**Commits:** {len(ticket.commits)} commit(s)

I'll now analyze the code changes and begin the TDD review process.

**Next steps:**
1. Analyze code changes
2. Generate/verify tests
3. Execute tests
4. Approve or reject code"""
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
