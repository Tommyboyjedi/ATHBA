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
from core.services.session_proxy import SessionProxy
from core.dataclasses.session_state import SessionState

class PmAgent(IAgent):


    def __init__(self, session: Projses, session_proxy: SessionProxy):
        self._session = session
        self.session_proxy = session_proxy
        self.ticket_repo = TicketRepo()
        self.behaviors = BehaviorLoader().load_for_agent(self)
        self.request = None

    async def initialize(self):
        self._project = await ProjectsController().get_project(self._session.project_id)

    async def run(self, content: str) -> list[ChatMessage]:
        exchange = LlmExchange(agent=self, session=self._session, content=content)
        intents = await exchange.get_intents()
        results: list = []

        # Repair pass if the LLM failed to return valid JSON/intents
        if not intents:
            repair_prompt = (
                "You are repairing a previous PM agent extraction that failed to return valid JSON. "
                "Return a valid JSON array of one or more objects following this exact schema per object: "
                "{\n  \"response\": \"<your_response_here>\",\n  \"intent\": \"<one_of: create_project | rename_project | edit_spec | remind_approval | confirm_action | basic_reply>\",\n  \"agents_routing\": [\"@AgentName\"],\n  \"entities\": {}\n}. "
                "Rules: 1) Output ONLY raw JSON (no code fences). 2) Include ALL fields. 3) If the user wants to work on the specification or provides concrete requirements/stack details, set intent to 'edit_spec' and include ['@Spec'] in agents_routing. 4) If no specific action, use 'basic_reply'. 5) Keep entities an empty object unless you have a specific key like project_name for create_project.\n\n"
                f"User input: {content}\n\nReturn only the JSON array."
            )
            repaired = await exchange.infer_with_prompt(repair_prompt)
            if repaired:
                intents = repaired
            else:
                return [ChatMessage(sender=self.name, content="I couldn't parse that. Could you rephrase?")]

        for intent in intents:
            print("LLM INTENT:", intent.intent)
            print("LLM RAW RESPONSE:", repr(intent.response))
            for behavior in self.behaviors:
                messages = await behavior.run(self, content, intent)
                if messages:
                    if isinstance(messages, list):
                        results.extend(messages)
                    else:
                        results.append(messages)

            # Multi-agent routing directives
            try:
                for route in intent.agents_routing or []:
                    agent_name = route[1:] if isinstance(route, str) and route.startswith("@") else route
                    if agent_name and agent_name != self.name:
                        results.append(SessionState(agent_name=agent_name))
            except Exception:
                pass

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

    async def log(self, message: str):
        print(f"[{self.name}][{self._session.project_id}] {message}")

    @property
    def llm_prompt(self) -> str:
        return f"""You are the Project Manager (PM) agent in an AI-driven DevOps team.

    Respond with a valid JSON array containing one or more objects. Each object must have these exact fields:
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
    1. The response MUST be valid JSON (no code fences)
    2. Include ALL fields in each object
    3. Use agents_routing (e.g., ["@Spec"]) when another agent should act this turn
    4. Keep entities as an empty object if no entities are extracted

    Examples:
    User: "Let's start a new project called 'Customer Portal' and update the login spec."
    [
      {{
        "response": "I'll create a new project called 'Customer Portal'.",
        "intent": "create_project",
        "agents_routing": ["@Spec"],
        "entities": {{"project_name": "Customer Portal"}}
      }},
      {{
        "response": "Routing to Spec to update the login section.",
        "intent": "edit_spec",
        "agents_routing": ["@Spec"],
        "entities": {{"section": "login"}}
      }}
    ]

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
