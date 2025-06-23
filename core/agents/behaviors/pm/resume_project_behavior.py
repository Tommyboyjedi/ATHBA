from core.agents.interfaces import AgentBehavior
from core.agents.pm_agent import PmAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.project_service import ProjectsService


class ResumeProjectBehavior(AgentBehavior):
    intent = ["resume_project", "reactivate_project"]

    async def run(self, agent: PmAgent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return None

        project_id = str(agent.session.project_id)
        project = await ProjectsService().get_project_by_id(project_id)
        project.paused = False
        await ProjectsService().update_project(project)

        return AgentMessage(
            sender=agent.name,
            text="Project resumed. Agents may now continue their tasks."
        )
