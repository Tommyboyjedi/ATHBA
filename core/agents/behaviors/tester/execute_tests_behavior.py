"""
Execute Tests Behavior for Tester Agent.

This behavior executes tests using pytest and captures results.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from datetime import datetime
from core.dataclasses.history_entry import HistoryEntry


class ExecuteTestsBehavior(AgentBehavior):
    """
    Behavior for executing tests with pytest.
    
    When triggered, this behavior:
    1. Runs pytest on ticket's branch
    2. Captures test results (passed/failed/errors)
    3. Updates ticket with test pass rate
    4. Provides detailed feedback
    """
    
    intent = ["execute_tests", "run_tests", "test", "pytest"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the execute tests behavior.
        
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
        
        # Get test files if specified
        test_files = None
        if ticket.test_files:
            test_files = ticket.test_files
        
        # Execute tests
        results = await agent.test_service.run_tests(
            agent.project.id,
            test_files=test_files,
            verbose=True
        )
        
        # Update ticket with results
        ticket.test_results = results
        ticket.test_pass_rate = results.get("pass_rate", 0.0)
        
        # Add history entry
        status_emoji = "✅" if results["status"] == "success" else "❌" if results["status"] == "failure" else "⚠️"
        ticket.history.append(HistoryEntry(
            timestamp=datetime.utcnow(),
            agent="Tester",
            action="execute_tests",
            details=f"{status_emoji} Tests executed: {results['passed']}/{results['total']} passed ({results['pass_rate']*100:.1f}%)"
        ))
        
        ticket.updated_at = datetime.utcnow()
        await agent.ticket_repo.update(ticket)
        
        # Format response based on results
        status_emoji = "✅" if results["status"] == "success" else "❌" if results["status"] == "failure" else "⚠️"
        
        response_msg = f"""{status_emoji} **Test Execution Complete**

**Branch:** {ticket.branch_name}
**Status:** {results['status'].upper()}

**Results:**
- ✅ Passed: {results['passed']}
- ❌ Failed: {results['failed']}
- ⚠️ Errors: {results['errors']}
- ⏭️ Skipped: {results['skipped']}
- 📊 Total: {results['total']}
- 📈 Pass Rate: {results['pass_rate']*100:.1f}%
- ⏱️ Duration: {results['duration']:.2f}s

"""
        
        # Add output if there were failures or errors
        if results['failed'] > 0 or results['errors'] > 0:
            # Truncate output if too long
            output = results.get('output', '')
            if len(output) > 1000:
                output = output[-1000:]
                response_msg += f"**Test Output (last 1000 chars):**\n```\n{output}\n```\n\n"
            else:
                response_msg += f"**Test Output:**\n```\n{output}\n```\n\n"
            
            response_msg += "**Next steps:**\n"
            response_msg += "- Review failures and provide feedback to Developer\n"
            response_msg += "- Use 'reject code' to send back for fixes\n"
        else:
            response_msg += "**Next steps:**\n"
            response_msg += "- Verify code quality and test coverage\n"
            response_msg += "- Use 'approve code' if everything looks good\n"
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
