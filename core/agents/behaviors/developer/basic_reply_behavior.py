"""
Basic Reply Behavior for Developer Agent.

This behavior handles general conversation that doesn't match other intents.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class BasicReplyBehavior(AgentBehavior):
    """
    Behavior for handling general conversation.
    
    This is the fallback behavior when no other intent matches.
    It provides helpful information about Developer agent capabilities.
    """
    
    intent = ["basic_reply"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the basic reply behavior.
        
        Args:
            agent: Developer agent instance
            user_input: User's input message
            llm_response: LLM intent detection response
            
        Returns:
            List of ChatMessage responses, or None if not applicable
        """
        if llm_response.intent not in self.intent:
            return None
        
        # Get ticket status for context
        tickets = await agent.ticket_repo.list_all(agent.session.project_id)
        backlog_count = len([t for t in tickets if t.column == "Backlog"])
        assigned_count = len([t for t in tickets if agent.name in t.agents])
        in_progress_count = len([t for t in tickets if agent.name in t.agents and t.column == "In Progress"])
        
        response_text = f"""Hello! I'm the Developer Agent. I'm responsible for implementing tickets by writing code.

**Current Project Status**:
- Tickets in Backlog: {backlog_count}
- Tickets assigned to me: {assigned_count}
- Tickets in progress: {in_progress_count}

**My capabilities**:
1. 📋 **Claim tickets** - I can claim tickets from the Backlog
2. 🌿 **Create branches** - I create Git branches for tickets
3. 🔍 **Analyze tickets** - I analyze requirements to understand what to build
4. 💻 **Generate code** - I write code to implement features
5. 💾 **Commit code** - I commit code to Git with proper messages
6. 🔎 **Request review** - I request code review from the Tester agent

**Example commands**:
- "Claim a ticket" - I'll pick the highest priority ticket from Backlog
- "Create a branch for ticket <id>" - I'll create a Git branch
- "Analyze the ticket" - I'll break down the requirements
- "Generate code for this ticket" - I'll write the implementation
- "Commit the code" - I'll commit to Git
- "Request code review" - I'll move to Review for Tester

How can I help you today?"""
        
        # If there's a ticket in progress, mention it
        if in_progress_count > 0:
            in_progress_tickets = [t for t in tickets if agent.name in t.agents and t.column == "In Progress"]
            ticket = in_progress_tickets[0]
            response_text += f"\n\n**Currently working on**: {ticket.title}"
            if ticket.branch_name:
                response_text += f"\n**Branch**: `{ticket.branch_name}`"
        
        return [ChatMessage(
            sender=agent.name,
            content=response_text
        )]
