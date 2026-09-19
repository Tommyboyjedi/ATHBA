import uuid
from core.agents.interfaces import BehaviorExecution
from core.agents.pm_agent import PmAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from core.services.project_service import ProjectsService


class RenameProjectBehavior:
    intent = ["rename_project", "change_project_name", "update_project_name"]

    async def run(self, execution: BehaviorExecution) -> AgentMessage | None:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent not in self.intent:
            return None
        project_id = str(agent.session.project_id)
        new_name = llm_response.entities.get("projectName", "").strip()

        if not project_id or not new_name:
            return AgentMessage(
                sender=agent.name,
                text="I need both a project ID and a new name to rename a project.",
                session=agent.session,
            )

        await agent.log(f"Renaming project {project_id} to '{new_name}'")

        service = ProjectsService()
        updated_project = await service.rename_project(project_id, new_name)

        if updated_project:
            return AgentMessage(
                sender=agent.name,
                text=f"Project was successfully renamed to **{new_name}**.",
                session=agent.session,
            )
        else:
            return AgentMessage(
                sender=agent.name,
                text=f"Sorry, I couldn’t find a project with ID `{project_id}`.",
                session=agent.session,
            )
