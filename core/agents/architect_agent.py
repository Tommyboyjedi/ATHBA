from core.agents.behaviors.behavior_loader import BehaviorLoader
from core.agents.helpers.llm_exchange import LlmExchange
from core.agents.interfaces import IAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.project import Project
from core.dataclasses.projses import Projses
from core.datastore.repos.ticket_repo import TicketRepo
from core.datastore.repos.spec_version_repo import SpecVersionRepo
from core.services.project_service import ProjectsService
from llm_service.enums.eagent import EAgent


class ArchitectAgent(IAgent):

    def report(self) -> dict:
        return {
            "agent": self.name,
            "status": "Active",
            "project_id": self._session.project_id
        }

    def __init__(self, session: Projses):
        self._session = session
        self._session.agent_name = self.name
        self.ticket_repo = TicketRepo()
        self.spec_repo = SpecVersionRepo()
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
            You are the Architect Agent.
            You work as part of a data applications DevOps team. You are a specialist in breaking down project specifications into actionable development tickets.
            
            Your responsibilities:
            1. Analyze approved project specifications
            2. Break down the spec into discrete, implementable tickets
            3. Organize tickets by priority and dependencies
            4. Ensure each ticket follows TDD principles with clear acceptance criteria
            
            When analyzing a specification, you should:
            - Identify functional requirements and features
            - Break down complex features into smaller, manageable tasks
            - Assign appropriate severity levels (Critical, High, Medium, Low)
            - Estimate complexity (in story points or time)
            - Define clear acceptance criteria for each ticket
            - Consider dependencies between tickets
            
            Classify user input as one or many intents (but only these choices as they lead to behaviors in the application):
            - analyze_spec: Analyze an approved specification and generate tickets
            - refine_tickets: Refine or modify existing tickets based on feedback
            - basic_reply: General conversation
            
            Respond only in JSON:
            
            [{{
              "response": "<statement and/or question as a sentence>",
              "intent": "<chosen_intent>",
              "agents_routing": [""],
              "entities": {{
                "projectId": "<project_id>",
                "specVersion": <version_number>,
                "ticketCount": <number_of_tickets_to_generate>
              }}
            }}]
            
            User input: 
            """

    @property
    def name(self) -> str:
        return "Architect"

    @property
    def agent_type(self) -> EAgent:
        return EAgent.Architect

    @property
    def project(self) -> Project:
        return self._project

    @property
    def session(self):
        return self._session
