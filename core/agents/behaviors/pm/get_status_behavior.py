from core.agents.interfaces import AgentBehavior
from core.agents.pm_agent import PmAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.project_service import ProjectsService


class GetStatusBehavior(AgentBehavior):
    intent = ["get_status", "get_update","status_update", "project_status", 'current_status','status','summary']

    async def run(self, agent: PmAgent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return None

        project_id = str(agent.session.project_id)
        stats = await ProjectsService().get_ticket_stats(project_id)

        message = (
            f"Here’s the current project status:\n"
            f"- Open tickets: {stats.get('open', 0)}\n"
            f"- Done tickets: {stats.get('done', 0)}"
        )

        return AgentMessage(sender=agent.name, text=message)
