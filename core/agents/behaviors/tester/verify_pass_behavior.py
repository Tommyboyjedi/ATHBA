"""
Verify Pass Behavior for Tester Agent.

This behavior verifies that all tests pass (TDD GREEN phase).
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class VerifyPassBehavior(AgentBehavior):
    """
    Behavior for verifying tests pass (TDD GREEN phase).
    
    When triggered, this behavior:
    1. Checks latest test results
    2. Confirms all tests pass
    3. Suggests next steps (approve or refactor)
    """
    
    intent = ["verify_pass", "verify", "check_pass", "tdd_green"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the verify pass behavior.
        
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
        
        # Check if tests have been run
        if not ticket.test_results:
            return [ChatMessage(
                sender=agent.name,
                content="⚠️ No test results available. Run 'execute tests' first."
            )]
        
        # Check test status
        status = ticket.test_results.get("status")
        passed = ticket.test_results.get("passed", 0)
        total = ticket.test_results.get("total", 0)
        pass_rate = ticket.test_pass_rate
        
        if status == "success":
            # All tests pass - GREEN phase complete
            response_msg = f"""✅ **TDD GREEN Phase Complete!**

**Ticket:** {ticket.title}

**Test Status:** ALL PASSING ✓
- ✅ Passed: {passed}/{total}
- 📊 Pass Rate: {pass_rate*100:.1f}%
- ⏱️ Duration: {ticket.test_results.get('duration', 0):.2f}s

**TDD Cycle Status:**
1. ✅ RED: Tests written first
2. ✅ GREEN: Code passes all tests
3. 🔵 REFACTOR: Optional - improve code quality

**Next steps:**
- If code quality is good: Use 'approve code'
- If refactoring needed: Request Developer to refactor
- If more tests needed: Add more tests and re-verify"""
            
        else:
            # Tests still failing
            failed = ticket.test_results.get("failed", 0)
            errors = ticket.test_results.get("errors", 0)
            
            response_msg = f"""❌ **Still in RED Phase**

**Ticket:** {ticket.title}

**Test Status:** FAILING
- ✅ Passed: {passed}/{total}
- ❌ Failed: {failed}
- ⚠️ Errors: {errors}
- 📊 Pass Rate: {pass_rate*100:.1f}%

**TDD Status:**
1. ✅ RED: Tests written
2. ❌ GREEN: Code NOT passing yet
3. ⏸️ REFACTOR: Cannot proceed

**Next steps:**
- Developer needs to fix failing tests
- Use 'reject code' to return to Developer with feedback
- Or wait for Developer to fix and re-run tests"""
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
