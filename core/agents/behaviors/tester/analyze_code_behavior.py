"""
Analyze Code Behavior for Tester Agent.

This behavior allows the Tester agent to analyze code changes on a ticket's branch.
"""

from datetime import datetime

from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.history_entry import HistoryEntry


class AnalyzeCodeBehavior:
    intent = ["analyze_code", "review_code", "check_code"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        agent = execution.agent
        llm_response = execution.intent
        if llm_response.intent not in self.intent:
            return None
        if not hasattr(agent.session, "current_ticket") or not agent.session.current_ticket:
            return [ChatMessage(sender=agent.name, content="❌ No ticket claimed. Use 'claim review' first.")]
        ticket = await agent.ticket_repo.get_ticket_by_id(agent.session.current_ticket)
        if not ticket:
            return [ChatMessage(sender=agent.name, content="❌ Current ticket not found.")]
        if not ticket.branch_name:
            return [ChatMessage(sender=agent.name, content="❌ No branch associated with this ticket.")]
        try:
            branch_status = await agent.git_service.get_branch_status(agent.project.id, ticket.branch_name)
        except Exception as error:
            return [ChatMessage(sender=agent.name, content=f"❌ Error getting branch status: {error}")]
        commits = branch_status.get("commits", [])
        if not commits:
            return [ChatMessage(sender=agent.name, content="⚠️ No commits found on this branch yet.")]
        files_changed = list({file_name for commit in commits for file_name in commit.get("files_changed", [])})
        analysis_prompt = f"""Analyze this code change for testing:

**Ticket:** {ticket.title}
**Description:** {ticket.description}

**Files Changed:**
{chr(10).join(f'- {file_name}' for file_name in files_changed)}

**Commits:** {len(commits)} commit(s)

Provide:
1. Summary of what was implemented
2. Key functions/classes that need testing
3. Edge cases to consider
4. Recommended test coverage areas

Keep response concise and focused on testing needs."""
        from core.agents.helpers.llm_exchange import LlmExchange, LlmExchangeRequest

        tier = agent.escalation_manager.get_current_tier(ticket, "Tester")
        analysis = await LlmExchange(
            LlmExchangeRequest(agent=agent, session=agent.session, content=analysis_prompt, tier=tier, use_cloud=False)
        ).get_response()
        ticket.history.append(
            HistoryEntry(
                timestamp=datetime.utcnow(),
                agent="Tester",
                action="analyze_code",
                details=f"Analyzed {len(files_changed)} file(s) on branch {ticket.branch_name}",
            )
        )
        ticket.updated_at = datetime.utcnow()
        await agent.ticket_repo.update(ticket)
        response_msg = f"""🔍 **Code Analysis Complete**

**Branch:** {ticket.branch_name}
**Commits:** {len(commits)}
**Files Changed:** {len(files_changed)}

{', '.join(files_changed) if files_changed else 'No files'}

**Analysis:**
{analysis}

**Next step:** Generate tests to verify this implementation."""
        return [ChatMessage(sender=agent.name, content=response_msg)]
