"""
Request Review Behavior for Developer Agent.

This behavior requests code review from the Tester agent.
"""

from datetime import datetime
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.history_entry import HistoryEntry


class RequestReviewBehavior(AgentBehavior):
    """
    Behavior for requesting code review from Tester.
    
    When triggered, this behavior:
    1. Verifies ticket has committed code
    2. Moves ticket to "Review" column
    3. Notifies that Tester should review
    4. Updates ticket history
    """
    
    intent = ["request_review"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the request review behavior.
        
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
                    content="❌ No ticket in progress. Please claim and work on a ticket first."
                )]
            
            ticket = assigned_tickets[0]
        else:
            ticket = await agent.ticket_repo.get(ticket_id)
        
        if not ticket:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Ticket {ticket_id} not found."
            )]
        
        # Check if ticket has commits
        if not ticket.commits or len(ticket.commits) == 0:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No code has been committed for this ticket. Please commit code before requesting review."
            )]
        
        # Get branch status to show what's being reviewed
        branch_status = None
        try:
            branch_status = await agent.git_service.get_branch_status(
                agent.session.project_id,
                ticket.branch_name
            )
        except Exception:
            pass  # Continue even if we can't get branch status
        
        # Move ticket to Review column
        updates = {
            "column": "Review",
            "agents": [agent.name, "Tester"],  # Add Tester to agents list
            "history": ticket.history + [HistoryEntry(
                timestamp=datetime.utcnow(),
                event="review_requested",
                actor=agent.name,
                details=f"Code review requested from Tester agent"
            )]
        }
        
        updated_ticket = await agent.ticket_repo.update(ticket.id, updates)
        
        if not updated_ticket:
            return [ChatMessage(
                sender=agent.name,
                content="❌ Failed to request review. Please try again."
            )]
        
        # Build commit summary
        commit_summary = f"{len(ticket.commits)} commit(s)"
        if branch_status and branch_status.get("commits"):
            commits_list = "\n".join([
                f"  - {c['sha']}: {c['message']}"
                for c in branch_status["commits"][:5]  # Show max 5 commits
            ])
            commit_summary = f"""
**Commits** ({len(branch_status['commits'])} total):
{commits_list}
"""
        
        return [ChatMessage(
            sender=agent.name,
            content=f"""✅ Code review requested!

**Ticket**: {ticket.title}
**Branch**: `{ticket.branch_name}`
**Status**: Moved to "Review"

{commit_summary}

The Tester agent will now:
1. Review the code changes
2. Run tests to verify functionality
3. Either approve the changes or request modifications

You'll be notified once the review is complete."""
        )]
