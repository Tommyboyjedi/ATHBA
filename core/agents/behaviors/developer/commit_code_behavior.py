"""
Commit Code Behavior for Developer Agent.

This behavior commits generated code to the Git branch.
"""

from datetime import datetime
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.history_entry import HistoryEntry


class CommitCodeBehavior(AgentBehavior):
    """
    Behavior for committing code to Git.
    
    When triggered, this behavior:
    1. Takes pending code from session
    2. Writes files to Git repository
    3. Creates a commit with appropriate message
    4. Updates ticket with commit SHA
    5. Updates ticket history
    """
    
    intent = ["commit_code"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the commit code behavior.
        
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
                    content="❌ No ticket in progress. Please claim a ticket first."
                )]
            
            ticket = assigned_tickets[0]
        else:
            ticket = await agent.ticket_repo.get(ticket_id)
        
        if not ticket:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Ticket {ticket_id} not found."
            )]
        
        # Check if ticket has a branch
        if not ticket.branch_name:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No Git branch exists for this ticket. Please create a branch first."
            )]
        
        # Check for pending code in session
        if not hasattr(agent.session, 'pending_code') or not agent.session.pending_code:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No pending code to commit. Please generate code first."
            )]
        
        # Get commit message from entities or use default
        commit_message = f"Implement {ticket.title}"
        if llm_response.entities and "commitMessage" in llm_response.entities:
            commit_message = llm_response.entities["commitMessage"]
        
        # Commit the code
        try:
            result = await agent.git_service.commit_files(
                agent.session.project_id,
                agent.session.pending_code,
                commit_message
            )
        except Exception as e:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Failed to commit code: {str(e)}"
            )]
        
        # Update ticket with commit info
        commits = ticket.commits if ticket.commits else []
        commits.append(result["commit_sha"])
        
        updates = {
            "commits": commits,
            "history": ticket.history + [HistoryEntry(
                timestamp=datetime.utcnow(),
                event="code_committed",
                actor=agent.name,
                details=f"Committed code: {result['commit_sha'][:7]} - {commit_message}"
            )]
        }
        
        updated_ticket = await agent.ticket_repo.update(ticket.id, updates)
        
        # Clear pending code from session
        agent.session.pending_code = {}
        
        # Create formatted file list
        files_committed = "\n".join([f"  - {f}" for f in result["files"]])
        
        return [ChatMessage(
            sender=agent.name,
            content=f"""✅ Code committed successfully!

**Commit**: `{result['commit_sha'][:7]}`
**Branch**: `{result['branch']}`
**Message**: {commit_message}

**Files committed**:
{files_committed}

The code is now in the repository. Next steps:
1. Request code review from the Tester agent
2. Run tests to verify the implementation"""
        )]
