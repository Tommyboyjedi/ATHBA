import uuid

from core.agents.interfaces import AgentBehavior
from core.agents.pm_agent import PmAgent
from core.controllers.project_controller import ProjectsController
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class CreateProjectBehavior(AgentBehavior):
    intent = ["create_project", "create_new_project", "initiate_project", "project_creation"]

    async def run(self, agent: PmAgent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage]:
        if llm_response.intent in self.intent:
            await agent.log("Creating new project context for session.")
            project_name = llm_response.entities.get("project_name")
            if not project_name:
                project_name = llm_response.entities.get("projectName") or "New Project(" + uuid.uuid4().hex + ")"
            project = await ProjectsController().create_project(name=project_name)

            agent.request.session['pending_action'] = {
                'type': 'activate_project',
                'project_id': str(project.id),
                'project_name': project.name,
            }

            content = f"I have created the project '{project.name}'. Would you like to make it the active project? (yes/no)"

            return [ChatMessage(
                    sender=agent.name,
                    content=content,
                    metadata={"refresh_overview": True}
                )]
        else:
            return []
