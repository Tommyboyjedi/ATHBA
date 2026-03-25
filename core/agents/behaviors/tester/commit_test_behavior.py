"""
Commit Test Behavior for Tester Agent.

This behavior commits generated test files to the Git branch.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from datetime import datetime
from core.dataclasses.history_entry import HistoryEntry


class CommitTestBehavior(AgentBehavior):
    """
    Behavior for committing test files to Git.
    
    When triggered, this behavior:
    1. Gets pending test code from session
    2. Commits test files to ticket's branch
    3. Updates ticket with test file references
    4. Records commit in history
    """
    
    intent = ["commit_test", "save_test", "commit"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the commit test behavior.
        
        Args:
            agent: Tester agent instance
            user_input: User's input message
            llm_response: LLM intent detection response
            
        Returns:
            List of ChatMessage responses, or None if not applicable
        """
        if llm_response.intent not in self.intent:
            return None
        
        # Check if we have a current ticket
        if not hasattr(agent.session, 'current_ticket') or not agent.session.current_ticket:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No ticket claimed. Use 'claim review' first."
            )]
        
        # Check if we have pending tests
        if not hasattr(agent.session, 'pending_tests') or not agent.session.pending_tests:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No pending tests to commit. Use 'generate test' first."
            )]
        
        # Get the ticket
        ticket = await agent.ticket_repo.get_ticket_by_id(agent.session.current_ticket)
        if not ticket:
            return [ChatMessage(
                sender=agent.name,
                content="❌ Current ticket not found."
            )]
        
        # Check if branch exists
        if not ticket.branch_name:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No branch associated with this ticket."
            )]
        
        # Checkout the branch
        try:
            await agent.git_service.checkout_branch(
                agent.project.id,
                ticket.branch_name
            )
        except Exception as e:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Error checking out branch: {str(e)}"
            )]
        
        # Get pending tests
        test_files = agent.session.pending_tests
        
        # Commit tests
        try:
            commit_result = await agent.git_service.commit_files(
                agent.project.id,
                test_files,
                f"Add tests for ticket {ticket.id}: {ticket.title} (TDD RED phase)"
            )
            
            # Update ticket with test file references and commit
            for test_file in test_files.keys():
                if test_file not in ticket.test_files:
                    ticket.test_files.append(test_file)
            
            commit_sha = commit_result.get("commit_sha", "")
            if commit_sha and commit_sha not in ticket.commits:
                ticket.commits.append(commit_sha)
            
            # Add history entry
            ticket.history.append(HistoryEntry(
                timestamp=datetime.utcnow(),
                agent="Tester",
                action="commit_test",
                details=f"Committed {len(test_files)} test file(s) to branch {ticket.branch_name} (SHA: {commit_sha[:8]})"
            ))
            
            ticket.updated_at = datetime.utcnow()
            await agent.ticket_repo.update(ticket)
            
            # Clear pending tests from session
            agent.session.pending_tests = {}
            
            # Format response
            response_msg = f"""✅ **Tests Committed (TDD RED Phase)**

**Branch:** {ticket.branch_name}
**Commit SHA:** {commit_sha[:8]}

**Test Files:**
{chr(10).join(f'- {f}' for f in test_files.keys())}

**Status:** Tests committed and ready for Developer.

**TDD Workflow:**
1. ✅ RED: Tests written and committed
2. ⏸️ GREEN: Waiting for Developer to implement code
3. ⏸️ VERIFY: Will run tests after implementation

These tests should FAIL until Developer implements the required functionality.

**Next steps:**
- Developer implements code to pass tests
- Run 'execute tests' after Developer commits
- Verify tests pass (GREEN phase)
- Approve or reject based on results"""
            
            return [ChatMessage(
                sender=agent.name,
                content=response_msg
            )]
            
        except Exception as e:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Error committing tests: {str(e)}"
            )]
