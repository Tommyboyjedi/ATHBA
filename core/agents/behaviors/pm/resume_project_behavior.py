from core.agents.interfaces import BehaviorExecution
from core.agents.pm_agent import PmAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.project_service import ProjectsService


class ResumeProjectBehavior:
    intent = ["resume_project", "reactivate_project"]

    async def run(self, execution: BehaviorExecution) -> AgentMessage | None:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

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
