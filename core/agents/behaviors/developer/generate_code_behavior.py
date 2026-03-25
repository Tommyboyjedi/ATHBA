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
    Behavior for generating code to implement a ticket.
    
    When triggered, this behavior:
    1. Retrieves the ticket details
    2. Uses LLM to generate code based on requirements
    3. Saves generated code to memory (not yet committed)
    4. Provides code preview to user
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
        
        # Use LLM to generate code
        code_prompt = f"""Generate clean, production-ready code for this ticket:

Title: {ticket.title}
Description: {ticket.description}
Label: {ticket.label}

Requirements:
1. Write clean, readable code with proper documentation
2. Follow best practices and design patterns
3. Include error handling
4. Add unit tests if appropriate
5. Use meaningful variable and function names

Please provide:
1. File path (where this code should go)
2. Complete code implementation
3. Brief explanation of the approach

Format your response as:
FILE: <file_path>
```
<code>
```
EXPLANATION: <brief explanation>
"""
        
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
