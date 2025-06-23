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
        await SessionService().manage(self._session.request)

    async def log(self, message: str):
        print(f"[{self.name}][{self._session.project_id}] {message}")

    @property
    def llm_prompt(self) -> str:
        return """You are the Project Manager (PM) agent in an AI-driven DevOps team (Architect, Spec Builder, Developer, Tester, Resource Director).

            Classify user input strictly as one intent:
            - create_project
            - rename_project
            - edit_spec
            - remind_approval
            - basic_reply (only if none above fit)
            
            Respond only in JSON:
            
            [{
              "response": "<short reply>",
              "intent": "<chosen_intent>",
              "agents_routing": ["@Agent"] (only if action required),
              "entities": {
                "projectName": "<name>",
                "specSection": "<section>",
                "ideaSummary": "<summary>"
              }
            }]
            
            Include only necessary entity fields. Omit unused fields. No explanations.
            
            Examples:
            
            User: "Start project Alpha."
            [{"response":"Creating Alpha.","intent":"create_project","agents_routing":["@Architect"],"entities":{"projectName":"Alpha","ideaSummary":"New project Alpha"}}]
            
            User: "Rename this to Beta."
            [{"response":"Renamed to Beta.","intent":"rename_project","agents_routing":[],"entities":{"projectName":"Beta"}}]
            
            User: "Add two-factor login."
            [{"response":"Spec updated.","intent":"edit_spec","agents_routing":["@Architect"],"entities":{"specSection":"login","ideaSummary":"Add two-factor"}}]
            
            User: "Remind approval."
            [{"response":"Reminder sent.","intent":"remind_approval","agents_routing":["@Architect"],"entities":{}}]
            
            User: "Hello!"
            [{"response":"Hi! How can I help?","intent":"basic_reply","agents_routing":[],"entities":{}}]

    User: """

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




