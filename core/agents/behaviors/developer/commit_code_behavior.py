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
    Behavior for committing code to Git with Uncle Bob's Law #1 enforcement.
    
    When triggered, this behavior:
    1. Validates tests exist (Uncle Bob's Law #1)
    2. Takes pending code from session
    3. Writes files to Git repository
    4. Creates a commit with appropriate message
    5. Updates ticket with commit SHA
    6. Updates ticket history
    
    Enforces Uncle Bob's Law #1: No production code unless it makes a failing test pass.
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
        
        # UNCLE BOB'S LAW #1: No production code unless it makes a failing test pass
        # Hard enforcement: tests must exist and be committed before production code
        if not ticket.test_files or len(ticket.test_files) == 0:
            return [ChatMessage(
                sender=agent.name,
                content="❌ **Uncle Bob's Law #1 Violation**\n\n**Rule:** You are not allowed to write any production code unless it is to make a failing unit test pass.\n\n**Enforcement:** Test files must be committed to the branch BEFORE production code can be committed. This ensures test-first development.\n\n**Action Required:** The Tester agent must generate and commit tests in the RED phase first. Then you can commit implementation code to make those tests pass (GREEN phase)."
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
