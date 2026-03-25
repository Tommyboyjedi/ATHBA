"""
Analyze Ticket Behavior for Developer Agent.

This behavior analyzes ticket requirements to understand what needs to be implemented.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class AnalyzeTicketBehavior(AgentBehavior):
    """
    Behavior for analyzing ticket requirements.
    
    When triggered, this behavior:
    1. Retrieves the ticket details
    2. Uses LLM to analyze requirements
    3. Provides implementation guidance
    4. Identifies potential challenges
    """
    
    intent = ["analyze_ticket"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the analyze ticket behavior.
        
        Args:
            agent: Developer agent instance
            user_input: User's input message
            llm_response: LLM intent detection response
            
        Returns:
            List of ChatMessage responses, or None if not applicable
        """
        if llm_response.intent not in self.intent:
            return None
        
        # Get ticket ID from entities
        ticket_id = None
        if llm_response.entities and "ticketId" in llm_response.entities:
            ticket_id = llm_response.entities["ticketId"]
        
        if not ticket_id:
            # Try to find a ticket assigned to this agent in "In Progress"
            tickets = await agent.ticket_repo.list_all(agent.session.project_id)
            assigned_tickets = [t for t in tickets if agent.name in t.agents and t.column == "In Progress"]
            
            if not assigned_tickets:
                return [ChatMessage(
                    sender=agent.name,
                    content="❌ No ticket in progress. Please claim a ticket and create a branch first."
                )]
            
            ticket = assigned_tickets[0]
        else:
            ticket = await agent.ticket_repo.get(ticket_id)
        
        if not ticket:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Ticket {ticket_id} not found."
            )]
        
        # Use LLM to analyze the ticket
        analysis_prompt = f"""Analyze this development ticket and provide implementation guidance:

Title: {ticket.title}
Description: {ticket.description}
Label: {ticket.label}
Severity: {ticket.severity}

Please provide:
1. Key requirements and acceptance criteria
2. Suggested implementation approach
3. Potential challenges or edge cases to consider
4. Recommended file structure or code organization
"""
        
        try:
            from core.agents.helpers.llm_exchange import LlmExchange
            llm_exchange = LlmExchange(
                agent=agent,
                session=agent.session,
                content=analysis_prompt,
                use_cloud=False
            )
            
            analysis = await llm_exchange.get_response()
        except Exception as e:
            analysis = f"Error analyzing ticket: {str(e)}\n\nPlease proceed with manual analysis."
        
        return [ChatMessage(
            sender=agent.name,
            content=f"""📋 **Ticket Analysis**

**Ticket**: {ticket.title}
**Label**: {ticket.label} | **Severity**: {ticket.severity}

**Description**:
{ticket.description}

---

**Analysis**:
{analysis}

---

Ready to generate code? Let me know what to implement!"""
        )]
