from core.agents.interfaces import AgentBehavior
from core.agents.pm_agent import PmAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.project_service import ProjectsService


class PauseProjectBehavior(AgentBehavior):
    intent = ["pause_project", "suspend_project"]

    async def run(self, agent: PmAgent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return None

        project_id = str(agent.session.project_id)
        project = await ProjectsService().get_project_by_id(project_id)
        project.paused = True
        await ProjectsService().update_project(project)

        return AgentMessage(
            sender=agent.name,
            text="Project paused. All agents will suspend activity until resumed."
        )
