"""
Approve Code Behavior for Tester Agent.

This behavior approves code that passes all tests and moves ticket to Done.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from datetime import datetime
from core.dataclasses.history_entry import HistoryEntry


class ApproveCodeBehavior(AgentBehavior):
    """
    Behavior for approving code after tests pass.
    
    When triggered, this behavior:
    1. Verifies all tests pass
    2. Moves ticket to "Done" column
    3. Records approval in history
    4. Resets failure counters
    """
    
    intent = ["approve_code", "approve", "accept_code", "lgtm"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the approve code behavior.
        
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
        
        # Verify tests have been run
        if not ticket.test_results:
            return [ChatMessage(
                sender=agent.name,
                content="⚠️ No test results found. Run 'execute tests' first."
            )]
        
        # Check if tests pass
        if ticket.test_results.get("status") != "success":
            return [ChatMessage(
                sender=agent.name,
                content=f"""❌ Cannot approve - tests are not passing.

**Status:** {ticket.test_results.get('status', 'unknown').upper()}
**Pass Rate:** {ticket.test_pass_rate*100:.1f}%
**Failed:** {ticket.test_results.get('failed', 0)}
**Errors:** {ticket.test_results.get('errors', 0)}

Please fix failing tests before approval."""
            )]
        
        # Move ticket to Done
        old_column = ticket.column
        ticket.column = "Done"
        
        # Add approval history entry
        ticket.history.append(HistoryEntry(
            timestamp=datetime.utcnow(),
            agent="Tester",
            action="approve_code",
            details=f"Code approved! All {ticket.test_results.get('total', 0)} tests passing. Moved from {old_column} to Done."
        ))
        
        ticket.updated_at = datetime.utcnow()
        
        # Reset failure counters on both Developer and Tester
        await agent.escalation_manager.record_success(ticket, "Developer")
        await agent.escalation_manager.record_success(ticket, "Tester")
        
        # Save ticket
        await agent.ticket_repo.update(ticket)
        
        # Clear session ticket
        agent.session.current_ticket = None
        
        # Format response
        response_msg = f"""✅ **Code Approved!**

**Ticket:** {ticket.title}
**ID:** {ticket.id}

**Test Results:**
- ✅ All {ticket.test_results.get('total', 0)} tests passing
- 📊 Pass Rate: {ticket.test_pass_rate*100:.1f}%
- ⏱️ Duration: {ticket.test_results.get('duration', 0):.2f}s

**Status:** Moved to Done ✓

This ticket is complete and ready for deployment!

**TDD Cycle Complete:**
1. ✅ Tests written first (RED phase)
2. ✅ Code implemented (GREEN phase)
3. ✅ Tests verified (All passing)
4. ✅ Code approved"""
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
