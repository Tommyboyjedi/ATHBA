from core.agents.behaviors.behavior_loader import BehaviorLoader
from core.agents.helpers.llm_exchange import LlmExchange
from core.agents.interfaces import IAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.project import Project
from core.dataclasses.projses import Projses
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.project_service import ProjectsService
from llm_service.enums.eagent import EAgent


class SpecBuilderAgent(IAgent):

    def report(self) -> dict:
        return {"agent": self.name, "status": "Idle", "project_id": getattr(self._session, "project_id", None)}

    def __init__(self, session: Projses):
        self._session = session
        self._session.agent_name = self.name
        self.ticket_repo = TicketRepo()
        self.behaviors = BehaviorLoader().load_for_agent(self)

    async def initialize(self):
        self._project = await ProjectsService().get_project_by_id(self._session.project_id)

    async def run(self, content: str) -> list[ChatMessage]:
        response = await LlmExchange(agent=self, session=self._session, content=content).get_intent()
        results = []

        for behavior in self.behaviors:
            messages = await behavior.run(self, content, response)
            if messages:
                if isinstance(messages, list):
                    results.extend(messages)
                else:
                    results.append(messages)

        return results

    @property
    def llm_prompt(self) -> str:
        return f"""
            You are the Specification Builder Agent.
            You work as part of an data applications devops team. You are specialist in prompting as much information from the human as possible to help drive the design of the software.
            After you have completed the specification an Architect will convert it into a design document, and then kanban tickets. 
            Your task is to take functional requirements or vague ideas from a user and produce structured, clear, and concise specification blocks.
            Format all output as markdown-compatible, plain English specification sections.
            
            Classify user input as one or many intents (but only these choices as they lead to behaviors in the application):
            - add_to_spec
            - ask_a_question
            - change_spec
            - start_spec
            - finalize_spec
            
            Respond only in JSON:
            
            [{
              "response": "<statement and.or question as a sentance>",
              "intent": "<chosen_intent>",
              "agents_routing": [""] (always empty),
              "entities": {
                "projectName": "<name>",
                "humanIdeas": ["<prose containing idea (summarised)>","<prose containing another idea (summarised)>"]
                "specSections": ["<name of spec section>","<name of another spec section>"],
              }
            }]
            
            User input: 
            """

    @property
    def name(self) -> str:
        return "Spec"

    @property
    def agent_type(self) -> EAgent:
        return EAgent.Spec

    @property
    def project(self) -> Project:
        return self._project

    @property
    def session(self):
        return self._session