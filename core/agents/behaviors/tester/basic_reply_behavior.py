"""
Basic Reply Behavior for Tester Agent.

This behavior handles general conversation and status queries.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class BasicReplyBehavior(AgentBehavior):
    """
    Behavior for general conversation and status queries.
    
    Handles intents that don't match other specific behaviors.
    """
    
    intent = ["basic_reply", "status", "help", "info"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the basic reply behavior.
        
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
        current_ticket_info = ""
        if hasattr(agent.session, 'current_ticket') and agent.session.current_ticket:
            ticket = await agent.ticket_repo.get_ticket_by_id(agent.session.current_ticket)
            if ticket:
                test_status = "Not run"
                if ticket.test_results:
                    status = ticket.test_results.get("status")
                    if status == "success":
                        test_status = f"✅ Passing ({ticket.test_pass_rate*100:.0f}%)"
                    else:
                        test_status = f"❌ Failing ({ticket.test_pass_rate*100:.0f}%)"
                
                current_ticket_info = f"""
**Current Ticket:** {ticket.title}
**ID:** {ticket.id}
**Column:** {ticket.column}
**Branch:** {ticket.branch_name or 'None'}
**Tests:** {test_status}
"""
        
        # Build response
        response_msg = f"""🧪 **Tester Agent Status**

I enforce TDD (Test-Driven Development) following Uncle Bob's rules.

**My Role:**
- Write tests BEFORE implementation (RED phase)
- Verify code passes tests (GREEN phase)
- Ensure code quality through testing
- Manage LLM escalation on repeated failures

{current_ticket_info}

**Available Commands:**
- `claim review` - Claim ticket from Review column
- `analyze code` - Analyze code changes
- `generate test` - Create tests (TDD RED)
- `execute tests` - Run pytest
- `verify pass` - Check if tests pass (TDD GREEN)
- `approve code` - Approve passing code
- `reject code` - Reject failing code
- `status` - Show this status

**TDD Workflow:**
1. 🔴 RED: Write failing test first
2. 🟢 GREEN: Developer makes test pass
3. 🔵 REFACTOR: Improve code quality
4. ✅ APPROVE: Move to Done

**LLM Escalation:** STANDARD → HEAVY → MEGA (after 3 failures each)

Need help with anything specific?"""
        
        # If there's a specific response from LLM, use it
        if llm_response.response and llm_response.response not in ["", "raw llm returned empty"]:
            response_msg = llm_response.response + "\n\n" + response_msg
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
