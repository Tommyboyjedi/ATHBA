"""
Generate Test Behavior for Tester Agent.

This behavior generates failing tests following TDD RED phase.
This is the core of the TDD workflow - test FIRST, then code.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from datetime import datetime
from core.dataclasses.history_entry import HistoryEntry


class GenerateTestBehavior(AgentBehavior):
    """
    Behavior for generating tests (TDD RED phase).
    
    When triggered, this behavior:
    1. Generates test code based on requirements
    2. Creates test file in tests/ directory
    3. Commits test to Git branch
    4. Ensures test FAILS initially (RED phase)
    5. Uses LLM escalation on repeated failures
    """
    
    intent = ["generate_test", "write_test", "create_test", "tdd_red"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the generate test behavior.
        
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
                content="❌ No branch associated with this ticket. Developer should create branch first."
            )]
        
        # Checkout the ticket's branch
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
        
        # Get current tier for this ticket/agent
        tier = agent.escalation_manager.get_current_tier(ticket, "Tester")
        
        # Generate test code with LLM
        test_prompt = f"""Generate pytest test code for this ticket following TDD RED phase and Uncle Bob's Law #2.

**Ticket:** {ticket.title}
**Description:** {ticket.description}

**Requirements (Uncle Bob's Law #2):**
1. Write the MINIMAL test sufficient to fail
2. Test should verify ONE specific requirement only
3. Stop as soon as you have a failing test
4. Compilation/import failures count as failures
5. Use proper pytest patterns (fixtures, parametrize, etc.)
6. Include docstrings

**IMPORTANT:** Do NOT write comprehensive tests or test edge cases. Write the simplest test that will fail because the implementation doesn't exist yet.

**Output format:**
Provide ONLY the Python test code, no explanations.
Use appropriate file name: test_<feature>.py

Generate the minimal test file:"""
        
        from core.agents.helpers.llm_exchange import LlmExchange
        
        try:
            test_code = await LlmExchange(
                agent=agent,
                session=agent.session,
                content=test_prompt,
                tier=tier,
                use_cloud=False
            ).get_response()
            
            # Extract code if wrapped in markdown
            if "```python" in test_code:
                test_code = test_code.split("```python")[1].split("```")[0].strip()
            elif "```" in test_code:
                test_code = test_code.split("```")[1].split("```")[0].strip()
            
            # Determine test file name
            # Sanitize title for filename
            import re
            safe_title = re.sub(r'[^\w\s-]', '', ticket.title.lower())
            safe_title = re.sub(r'[-\s]+', '_', safe_title)
            test_filename = f"tests/test_{safe_title}.py"
            
            # Store test code in session for commit
            if not hasattr(agent.session, 'pending_tests'):
                agent.session.pending_tests = {}
            
            agent.session.pending_tests[test_filename] = test_code
            
            # Record success (test generation succeeded)
            await agent.escalation_manager.record_success(ticket, "Tester")
            
            # Format response
            response_msg = f"""✅ **Test Generated (TDD RED Phase)**

**File:** {test_filename}
**Lines:** ~{len(test_code.split(chr(10)))} lines
**LLM Tier:** {tier.value.upper()}

```python
{test_code[:500]}...
```

**Status:** Test generated and ready to commit.
**Expected:** Test will FAIL (RED phase) until Developer implements code.

**Next steps:**
1. Commit this test to branch
2. Developer implements code to make test pass (GREEN phase)
3. Execute tests to verify

Use 'commit test' to save this test file."""
            
            return [ChatMessage(
                sender=agent.name,
                content=response_msg
            )]
            
        except Exception as e:
            # Record failure and potentially escalate
            ticket, new_tier = await agent.escalation_manager.record_failure(
                ticket,
                "Tester",
                f"Failed to generate test: {str(e)}"
            )
            
            return [ChatMessage(
                sender=agent.name,
                content=f"""❌ **Test Generation Failed**

**Error:** {str(e)}

**Failure Count:** {ticket.tester_failure_count}
**Current Tier:** {new_tier.value.upper()}

{'⚠️ Escalated to next LLM tier. Try again.' if ticket.tester_failure_count % 3 == 0 else 'Retrying with current tier.'}"""
            )]
