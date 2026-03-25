"""
Generate Code Behavior for Developer Agent.

This behavior generates code to implement a ticket using the LLM.
"""

from datetime import datetime
from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from core.dataclasses.history_entry import HistoryEntry


class GenerateCodeBehavior(AgentBehavior):
    """
    Behavior for generating code to implement a ticket following Uncle Bob's Law #3.
    
    When triggered, this behavior:
    1. Retrieves the ticket details and test files
    2. Reads existing test code to understand requirements
    3. Uses LLM to generate MINIMAL code to pass tests (Uncle Bob's Law #3)
    4. Saves generated code to memory (not yet committed)
    5. Provides code preview to user
    
    Enforces Uncle Bob's Law #3: Write only enough code to pass one failing test.
    """
    
    intent = ["generate_code"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the generate code behavior.
        
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
                    content="❌ No ticket in progress. Please claim a ticket and create a branch first."
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
        
        # UNCLE BOB'S LAW #1: Ensure tests exist before generating production code
        # This is a warning, not a hard block, because generate_code doesn't commit
        # The hard enforcement is in commit_code_behavior.py
        if not ticket.test_files or len(ticket.test_files) == 0:
            return [ChatMessage(
                sender=agent.name,
                content="⚠️ **Warning: No tests found**\n\nUncle Bob's Law #1: You must have a failing test before writing production code.\n\nTester should generate tests first. You may proceed to generate code, but **commit_code_behavior will block your commit** until tests exist.\n\nRecommendation: Wait for Tester to commit tests first."
            )]
        
        # Read the test file to understand what needs to be implemented
        test_code_context = ""
        if ticket.test_files:
            try:
                # Read the first test file to understand requirements
                test_file_path = ticket.test_files[0]
                repo_path = f"/tmp/athba_repos/{agent.project.id}"
                
                # Try to read test file
                import os
                full_test_path = os.path.join(repo_path, test_file_path)
                if os.path.exists(full_test_path):
                    with open(full_test_path, 'r') as f:
                        test_code_context = f.read()
            except Exception:
                # If we can't read test, proceed without context
                pass
        
        # Use LLM to generate code following Uncle Bob's Law #3
        code_prompt = f"""Generate code for this ticket following Uncle Bob's Law #3 of TDD.

**UNCLE BOB'S LAW #3:** You are not allowed to write any more production code than is sufficient to pass the one failing unit test.

**Ticket:** {ticket.title}
**Description:** {ticket.description}
**Label:** {ticket.label}

"""
        
        # Add test context if available
        if test_code_context:
            code_prompt += f"""**Existing Test (must pass):**
```python
{test_code_context}
```

"""
        
        code_prompt += """**Requirements (Uncle Bob's Law #3):**
1. Write ONLY the MINIMAL code needed to make the test pass
2. Do NOT add error handling unless the test validates it
3. Do NOT add features beyond what the test checks
4. Do NOT implement edge cases unless tested
5. Keep it simple - just make the test green
6. If no test exists yet, write minimal code for the requirement

**Output format:**
FILE: <file_path>
```
<minimal_code_implementation>
```
EXPLANATION: <brief explanation>

Generate the minimal implementation:"""
        
        try:
            from core.agents.helpers.llm_exchange import LlmExchange
            llm_exchange = LlmExchange(
                agent=agent,
                session=agent.session,
                content=code_prompt,
                use_cloud=False  # Use local LLM for code generation
            )
            
            generated_code = await llm_exchange.get_response()
        except Exception as e:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Error generating code: {str(e)}\n\nPlease try again or write the code manually."
            )]
        
        # Parse the generated code to extract file path and content
        # This is a simple parser - in production, you'd want more robust parsing
        file_path = None
        code_content = None
        explanation = ""
        
        lines = generated_code.split('\n')
        in_code_block = False
        code_lines = []
        
        for line in lines:
            if line.startswith('FILE:'):
                file_path = line.replace('FILE:', '').strip()
            elif line.startswith('```'):
                in_code_block = not in_code_block
                if not in_code_block and code_lines:
                    code_content = '\n'.join(code_lines)
            elif in_code_block:
                code_lines.append(line)
            elif line.startswith('EXPLANATION:'):
                explanation = line.replace('EXPLANATION:', '').strip()
        
        if not file_path or not code_content:
            # Fallback: treat entire response as code
            file_path = f"src/{ticket.id}.py"
            code_content = generated_code
        
        # Store code in session state (temporary, before commit)
        if not hasattr(agent.session, 'pending_code'):
            agent.session.pending_code = {}
        
        agent.session.pending_code[file_path] = code_content
        
        # Update ticket history
        updates = {
            "history": ticket.history + [HistoryEntry(
                timestamp=datetime.utcnow(),
                event="code_generated",
                actor=agent.name,
                details=f"Generated code for {file_path}"
            )]
        }
        await agent.ticket_repo.update(ticket.id, updates)
        
        # Truncate code preview if too long
        preview = code_content[:500] + "..." if len(code_content) > 500 else code_content
        
        return [ChatMessage(
            sender=agent.name,
            content=f"""✅ Code generated successfully!

**File**: `{file_path}`
**Ticket**: {ticket.title}

**Code Preview**:
```
{preview}
```

{explanation}

The code is ready to commit. Would you like me to commit it to the branch `{ticket.branch_name}`?"""
        )]
