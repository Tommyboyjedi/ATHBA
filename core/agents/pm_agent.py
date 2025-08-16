from core.agents.behaviors.behavior_loader import BehaviorLoader
from core.agents.helpers.llm_exchange import LlmExchange
from core.agents.interfaces import IAgent
from core.controllers.project_controller import ProjectsController
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.project import Project
from core.dataclasses.projses import Projses
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.session_service import SessionService
from llm_service.enums.eagent import EAgent

class PmAgent(IAgent):


    def __init__(self, session: Projses):
        self._session = session
        self.ticket_repo = TicketRepo()
        self.behaviors = BehaviorLoader().load_for_agent(self)
        self.request = None

    async def initialize(self):
        self._project = await ProjectsController().get_project(self._session.project_id)

    async def run(self, content: str) -> list[ChatMessage]:
        response = await LlmExchange(agent=self, session=self._session, content=content).get_intent()
        results = []
        print("LLM INTENT:", response.intent)
        print("LLM RAW RESPONSE:", repr(response.response))

        for behavior in self.behaviors:
            messages = await behavior.run(self, content, response)
            if messages:
                if isinstance(messages, list):
                    results.extend(messages)
                else:
                    results.append(messages)
        print("Behaviors returned:", results)
        return results

    async def report(self) -> dict:
        return {
            "agent": self.name,
            "status": "Monitoring",
            "project_id": self._session.project_id
        }

    async def set_project(self, project: Project):
        self._project = project
        self._session.project_id = project._id
        await SessionService().manage(self.request)

    async def log(self, message: str):
        print(f"[{self.name}][{self._session.project_id}] {message}")

    @property
    def llm_prompt(self) -> str:
        return f"""You are the Project Manager (PM) agent in an AI-driven DevOps team.

    You MUST respond with a valid JSON array containing exactly one object with these exact fields:
    {{
      "response": "<your_response_here>",
      "intent": "<one_of_the_intents>",
      "agents_routing": ["@AgentName1", "@AgentName2"],
      "entities": {{}}
    }}

    Available intents:
    - create_project: When user wants to start a new project
    - rename_project: When user wants to rename the current project
    - edit_spec: When user wants to modify the specification
    - remind_approval: When user asks about or requests approval status
    - confirm_action: When user confirms or denies a pending action (e.g., 'yes', 'no')
    - basic_reply: For general conversation that doesn't fit other intents

    Rules:
    1. The response MUST be valid JSON
    2. Include ALL fields in the response
    3. Keep agents_routing as an empty list if no routing is needed
    4. Keep entities as an empty object if no entities are extracted

    Examples:
    User: "Let's start a new project called 'Customer Portal'"
    {{
      "response": "I'll help you create a new project called 'Customer Portal'.",
      "intent": "create_project",
      "agents_routing": ["@Spec"],
      "entities": {{"project_name": "Customer Portal"}}
    }}

    User: "yes"
    {{
      "response": "Got it.",
      "intent": "confirm_action",
      "agents_routing": [],
      "entities": {{"confirmation": "yes"}}
    }}

    User: "no, don't do that"
    {{
      "response": "OK, I won't.",
      "intent": "confirm_action",
      "agents_routing": [],
      "entities": {{"confirmation": "no"}}
    }}

    User: "Update the login page spec"
    {{
      "response": "I'll update the login page specification.",
      "intent": "edit_spec",
      "agents_routing": ["@Spec"],
      "entities": {{"section": "login"}}
    }}

    User: "Hello!"
    {{
      "response": "Hi there! How can I assist you today?",
      "intent": "basic_reply",
      "agents_routing": [],
      "entities": {{}}
    }}

    Current conversation:
    """

    @property
    def name(self) -> str:
        return "PM"

    @property
    def agent_type(self) -> EAgent:
        return EAgent.PM

    @property
    def project(self) -> Project:
        return self._project

    @property
    def session(self):
        return self._session
