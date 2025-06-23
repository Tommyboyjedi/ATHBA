import uuid
from core.agents.interfaces import AgentBehavior
from core.agents.pm_agent import PmAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.project_service import ProjectsService


class RenameProjectBehavior(AgentBehavior):
    intent = ["rename_project", "change_project_name", "update_project_name"]

    async def run(self, agent: PmAgent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return None
        project_id = str(agent.session.project_id)
        new_name = llm_response.entities.get("projectName", "").strip()

        if not project_id or not new_name:
            return AgentMessage(
                sender=agent.name,
                text="I need both a project ID and a new name to rename a project."
            )

        await agent.log(f"Renaming project {project_id} to '{new_name}'")

        service = ProjectsService()
        updated_project = await service.rename_project(project_id, new_name)

        if updated_project:
            return AgentMessage(
                sender=agent.name,
                text=f"Project was successfully renamed to **{new_name}**."
            )
        else:
            return AgentMessage(
                sender=agent.name,
                text=f"Sorry, I couldn’t find a project with ID `{project_id}`."
            )
