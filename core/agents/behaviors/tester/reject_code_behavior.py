"""
Reject Code Behavior for Tester Agent.

This behavior rejects code that fails tests and returns ticket to Developer.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from datetime import datetime
from core.dataclasses.history_entry import HistoryEntry


class RejectCodeBehavior(AgentBehavior):
    """
    Behavior for rejecting code that fails tests.
    
    When triggered, this behavior:
    1. Documents reasons for rejection
    2. Moves ticket back to "In Progress"
    3. Records failure for escalation tracking
    4. Provides detailed feedback to Developer
    """
    
    intent = ["reject_code", "reject", "fail", "needs_work"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the reject code behavior.
        
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
        
        # Get rejection reason from user input or test results
        reason = "Code does not meet requirements"
        
        if ticket.test_results:
            if ticket.test_results.get("failed", 0) > 0:
                reason = f"{ticket.test_results['failed']} test(s) failing"
            elif ticket.test_results.get("errors", 0) > 0:
                reason = f"{ticket.test_results['errors']} test error(s)"
        
        # Extract custom reason from user input if provided
        if "because" in user_input.lower():
            custom_reason = user_input.lower().split("because")[1].strip()
            reason = custom_reason
        
        # Move ticket back to In Progress
        old_column = ticket.column
        ticket.column = "In Progress"
        
        # Remove Tester from agents, keep Developer
        if "Tester" in ticket.agents:
            ticket.agents.remove("Tester")
        if "Developer" not in ticket.agents:
            ticket.agents.append("Developer")
        
        # Add rejection history entry
        ticket.history.append(HistoryEntry(
            timestamp=datetime.utcnow(),
            agent="Tester",
            action="reject_code",
            details=f"Code rejected: {reason}. Moved from {old_column} to In Progress for Developer fixes."
        ))
        
        ticket.updated_at = datetime.utcnow()
        
        # Record failure for Developer (they couldn't pass the tests)
        ticket, new_tier = await agent.escalation_manager.record_failure(
            ticket,
            "Developer",
            reason
        )
        
        # Save ticket
        await agent.ticket_repo.update(ticket)
        
        # Clear session ticket
        agent.session.current_ticket = None
        
        # Format failure details
        failure_details = ""
        if ticket.test_results:
            failure_details = f"""
**Test Results:**
- ❌ Failed: {ticket.test_results.get('failed', 0)}
- ⚠️ Errors: {ticket.test_results.get('errors', 0)}
- ✅ Passed: {ticket.test_results.get('passed', 0)}
- 📊 Pass Rate: {ticket.test_pass_rate*100:.1f}%

**Test Output (last 500 chars):**
```
{ticket.test_results.get('output', '')[-500:]}
```
"""
        
        # Format response
        response_msg = f"""❌ **Code Rejected**

**Ticket:** {ticket.title}
**ID:** {ticket.id}

**Reason:** {reason}

{failure_details}

**Status:** Returned to Developer (In Progress)

**Developer Escalation:**
- Failure Count: {ticket.developer_failure_count}
- Current LLM Tier: {ticket.developer_llm_tier.upper()}
{' - ⚠️ Escalated to ' + new_tier.value.upper() + ' tier' if ticket.developer_failure_count % 3 == 0 else ''}

**Next steps for Developer:**
1. Review test failures
2. Fix the code to pass all tests
3. Commit fixes
4. Request review again"""
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
