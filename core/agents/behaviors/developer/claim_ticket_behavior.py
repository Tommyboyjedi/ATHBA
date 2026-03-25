"""
Claim Ticket Behavior for Developer Agent.

This behavior allows the Developer agent to claim tickets from the Backlog.
"""

from datetime import datetime
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.history_entry import HistoryEntry


class ClaimTicketBehavior(AgentBehavior):
    """
    Behavior for claiming a ticket from the Backlog.
    
    When triggered, this behavior:
    1. Finds available tickets in the Backlog
    2. Claims a specific ticket or the highest priority one
    3. Moves the ticket to "To Do" column
    4. Assigns the Developer agent to the ticket
    5. Updates ticket history
    """
    
    intent = ["claim_ticket"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the claim ticket behavior.
        
        Args:
            agent: Developer agent instance
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
            ticket = await agent.ticket_repo.get(ticket_id)
            if not ticket:
                return [ChatMessage(
                    sender=agent.name,
                    content=f"❌ Ticket {ticket_id} not found."
                )]
            
            if ticket.column != "Backlog":
                return [ChatMessage(
                    sender=agent.name,
                    content=f"❌ Ticket '{ticket.title}' is not in the Backlog (currently in {ticket.column})."
                )]
        else:
            # Get all backlog tickets for this project
            backlog_tickets = await agent.ticket_repo.get_backlog_tickets(agent.session.project_id)
            
            if not backlog_tickets:
                return [ChatMessage(
                    sender=agent.name,
                    content="❌ No tickets available in the Backlog. Please create tickets first."
                )]
            
            # Sort by severity (Critical > High > Medium > Low)
            severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
            backlog_tickets.sort(key=lambda t: severity_order.get(t.severity, 999))
            
            # Take the highest priority ticket
            ticket = backlog_tickets[0]
        
        # Update ticket: assign to Developer and move to "To Do"
        updates = {
            "agents": [agent.name],
            "column": "To Do",
            "history": ticket.history + [HistoryEntry(
                timestamp=datetime.utcnow(),
                event="claimed",
                actor=agent.name,
                details=f"Ticket claimed by {agent.name}"
            )]
        }
        
        updated_ticket = await agent.ticket_repo.update(ticket.id, updates)
        
        if not updated_ticket:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Failed to claim ticket {ticket.id}."
            )]
        
        # Return success message with ticket details
        return [ChatMessage(
            sender=agent.name,
            content=f"""✅ Successfully claimed ticket!

**Ticket**: {updated_ticket.title}
**ID**: {updated_ticket.id}
**Severity**: {updated_ticket.severity}
**Label**: {updated_ticket.label}

**Description**: 
{updated_ticket.description}

The ticket has been moved to "To Do". Next steps:
1. Create a Git branch for this ticket
2. Analyze the requirements
3. Generate code to implement the ticket"""
        )]
