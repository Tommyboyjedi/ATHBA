"""
Analyze Code Behavior for Tester Agent.

This behavior allows the Tester agent to analyze code changes on a ticket's branch.
"""

from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from datetime import datetime
from core.dataclasses.history_entry import HistoryEntry


class AnalyzeCodeBehavior(AgentBehavior):
    """
    Behavior for analyzing code changes on a branch.
    
    When triggered, this behavior:
    1. Gets the current ticket's branch
    2. Analyzes code changes using LLM
    3. Identifies what needs to be tested
    4. Provides feedback on code quality
    """
    
    intent = ["analyze_code", "review_code", "check_code"]
    
    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        """
        Execute the analyze code behavior.
        
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
        
        # Get branch status
        try:
            branch_status = await agent.git_service.get_branch_status(
                agent.project.id,
                ticket.branch_name
            )
        except Exception as e:
            return [ChatMessage(
                sender=agent.name,
                content=f"❌ Error getting branch status: {str(e)}"
            )]
        
        # Get commit information
        commits = branch_status.get("commits", [])
        if not commits:
            return [ChatMessage(
                sender=agent.name,
                content="⚠️ No commits found on this branch yet."
            )]
        
        # Get files changed
        files_changed = []
        for commit in commits:
            files = commit.get("files_changed", [])
            files_changed.extend(files)
        
        # Remove duplicates
        files_changed = list(set(files_changed))
        
        # Analyze with LLM
        analysis_prompt = f"""Analyze this code change for testing:

**Ticket:** {ticket.title}
**Description:** {ticket.description}

**Files Changed:**
{chr(10).join(f'- {f}' for f in files_changed)}

**Commits:** {len(commits)} commit(s)

Provide:
1. Summary of what was implemented
2. Key functions/classes that need testing
3. Edge cases to consider
4. Recommended test coverage areas

Keep response concise and focused on testing needs."""
        
        from core.agents.helpers.llm_exchange import LlmExchange
        
        # Get current tier for this ticket/agent
        tier = agent.escalation_manager.get_current_tier(ticket, "Tester")
        
        analysis = await LlmExchange(
            agent=agent,
            session=agent.session,
            content=analysis_prompt,
            tier=tier,
            use_cloud=False
        ).get_response()
        
        # Add history entry
        ticket.history.append(HistoryEntry(
            timestamp=datetime.utcnow(),
            agent="Tester",
            action="analyze_code",
            details=f"Analyzed {len(files_changed)} file(s) on branch {ticket.branch_name}"
        ))
        
        ticket.updated_at = datetime.utcnow()
        await agent.ticket_repo.update(ticket)
        
        # Format response
        response_msg = f"""🔍 **Code Analysis Complete**

**Branch:** {ticket.branch_name}
**Commits:** {len(commits)}
**Files Changed:** {len(files_changed)}

{', '.join(files_changed) if files_changed else 'No files'}

**Analysis:**
{analysis}

**Next step:** Generate tests to verify this implementation."""
        
        return [ChatMessage(
            sender=agent.name,
            content=response_msg
        )]
