"""
Create Branch Behavior for Developer Agent.

This behavior creates a Git branch for a ticket.
"""

from datetime import datetime
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.history_entry import HistoryEntry


class CreateBranchBehavior(AgentBehavior):
    """
    Behavior for creating a Git branch for a ticket.
    
    When triggered, this behavior:
    1. Initializes Git repository if needed
    2. Creates a branch named after the ticket
    3. Updates ticket with branch name
    4. Updates ticket history
    """
    
    intent = ["create_branch"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the create branch behavior.
        
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
            # Try to find a ticket assigned to this agent in "To Do"
            tickets = await agent.ticket_repo.list_all(agent.session.project_id)
            assigned_tickets = [t for t in tickets if agent.name in t.agents and t.column == "To Do"]
            
            if not assigned_tickets:
                return [ChatMessage(
                    sender=agent.name,
                    content="❌ No ticket specified. Please claim a ticket first or specify a ticket ID."
                )]
            
            ticket = assigned_tickets[0]
            ticket_id = ticket.id
        else:
            ticket = await agent.ticket_repo.get(ticket_id)
        
        if not ticket:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Ticket {ticket_id} not found."
            )]
        
        # Check if ticket already has a branch
        if ticket.branch_name:
            return [ChatMessage(
                sender=agent.name,
                content=f"ℹ️ Ticket already has branch: `{ticket.branch_name}`"
            )]
        
        # Initialize repository if it doesn't exist
        if not agent.git_service.repo_exists(agent.session.project_id):
            try:
                await agent.git_service.initialize_repo(
                    agent.session.project_id,
                    agent.project.title if hasattr(agent, '_project') else "Project"
                )
            except Exception as e:
                return [ChatMessage(
                    sender=agent.name,
                    content=f"❌ Failed to initialize Git repository: {str(e)}"
                )]
        
        # Generate branch name from ticket
        # Format: ticket/<id>-<sanitized-title>
        sanitized_title = "".join(c if c.isalnum() or c in ['-', '_'] else '-' 
                                  for c in ticket.title.lower())[:50]
        branch_name = f"ticket/{ticket.id}-{sanitized_title}"
        
        # Allow custom branch name from entities
        if llm_response.entities and "branchName" in llm_response.entities:
            branch_name = llm_response.entities["branchName"]
        
        # Create branch
        try:
            result = await agent.git_service.create_branch(
                agent.session.project_id,
                branch_name
            )
        except Exception as e:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Failed to create branch: {str(e)}"
            )]
        
        # Update ticket with branch name
        updates = {
            "branch_name": branch_name,
            "column": "In Progress",
            "history": ticket.history + [HistoryEntry(
                timestamp=datetime.utcnow(),
                event="branch_created",
                actor=agent.name,
                details=f"Created branch: {branch_name}"
            )]
        }
        
        updated_ticket = await agent.ticket_repo.update(ticket.id, updates)
        
        if not updated_ticket:
            return [ChatMessage(
                sender=agent.name,
                content=f"⚠️ Branch created but failed to update ticket."
            )]
        
        return [ChatMessage(
            sender=agent.name,
            content=f"""✅ Git branch created successfully!

**Branch**: `{branch_name}`
**Ticket**: {ticket.title}
**Status**: Moved to "In Progress"

The branch is ready for development. Next steps:
1. Analyze the ticket requirements
2. Generate code to implement the feature
3. Commit the code to this branch"""
        )]
