"""
Developer Agent module.

This module implements the Developer Agent, which is responsible for
claiming tickets, creating branches, generating code, and committing changes.
"""

from core.agents.behaviors.behavior_loader import BehaviorLoader
from core.agents.helpers.llm_exchange import LlmExchange
from core.agents.interfaces import IAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.project import Project
from core.dataclasses.projses import Projses
from core.datastore.repos.ticket_repo import TicketRepo
from core.datastore.repos.code_repo import CodeRepo
from core.services.project_service import ProjectsService
from core.services.git_service import GitService
from llm_service.enums.eagent import EAgent


class DeveloperAgent(IAgent):
    """
    Developer Agent for code generation and implementation.
    
    The Developer Agent is responsible for:
    - Claiming tickets from the Backlog
    - Creating Git branches for tickets
    - Analyzing ticket requirements
    - Generating code to implement tickets
    - Committing code to branches
    - Requesting code review from Tester
    
    Attributes:
        name: Agent name ("Developer")
        session: Current session (Projses object)
        ticket_repo: Repository for ticket operations
        code_repo: Repository for code storage
        git_service: Service for Git operations
        behaviors: List of loaded behaviors
    """
    
    def __init__(self, session: Projses):
        """
        Initialize the Developer Agent.
        
        Args:
            session: Session object containing project_id and agent_name
        """
        self._session = session
        self._session.agent_name = self.name
        self.ticket_repo = TicketRepo()
        self.code_repo = CodeRepo()
        self.git_service = GitService()
        self.behaviors = BehaviorLoader().load_for_agent(self)
    
    async def initialize(self):
        """
        Initialize the agent by loading project data.
        """
        self._project = await ProjectsService().get_project_by_id(self._session.project_id)
    
    async def run(self, content: str) -> list[ChatMessage]:
        """
        Process user input and execute appropriate behaviors.
        
        Uses local LLM (codellama-7b) for intent detection and code generation.
        
        Args:
            content: User input message
            
        Returns:
            List of ChatMessage responses from behaviors
        """
        # Developer uses local LLM (codellama-7b)
        response = await LlmExchange(
            agent=self,
            session=self._session,
            content=content,
            use_cloud=False  # Use local LLM for Developer
        ).get_intent()
        
        results = []
        
        for behavior in self.behaviors:
            messages = await behavior.run(self, content, response)
            if messages:
                if isinstance(messages, list):
                    results.extend(messages)
                else:
                    results.append(messages)
        
        return results
    
    def report(self) -> dict:
        """
        Generate a status report for this agent.
        
        Returns:
            Dictionary with agent status information
        """
        return {
            "agent": self.name,
            "status": "Active",
            "project_id": self._session.project_id
        }
    
    @property
    def llm_prompt(self) -> str:
        """
        Get the system prompt for the Developer Agent's LLM.
        
        Returns:
            System prompt string
        """
        return f"""
            You are the Developer Agent.
            You work as part of a TDD DevOps software development team. You are a specialist in writing high-quality code.
            
            Your responsibilities:
            1. Claim tickets from the Backlog
            2. Create Git branches for tickets
            3. Analyze ticket requirements and understand what needs to be implemented
            4. Generate clean, well-tested code that meets the requirements
            5. Commit code to Git branches
            6. Request code review from the Tester agent
            
            When generating code, you should:
            - Write clean, readable, and maintainable code
            - Follow TDD principles (write tests first when appropriate)
            - Add appropriate comments and documentation
            - Handle edge cases and errors properly
            - Follow the project's coding conventions
            
            Classify user input as one or many intents (but only these choices as they lead to behaviors in the application):
            - claim_ticket: Claim a ticket from the Backlog to work on
            - create_branch: Create a Git branch for a ticket
            - analyze_ticket: Analyze and understand ticket requirements
            - generate_code: Generate code to implement a ticket
            - commit_code: Commit generated code to Git
            - request_review: Request code review from Tester
            - basic_reply: General conversation
            
            Respond only in JSON:
            
            [{{
              "response": "<statement and/or question as a sentence>",
              "intent": "<chosen_intent>",
              "agents_routing": [""],
              "entities": {{
                "ticketId": "<ticket_id>",
                "branchName": "<branch_name>",
                "filePath": "<file_path>",
                "commitMessage": "<commit_message>"
              }}
            }}]
            
            User input: 
            """
    
    @property
    def name(self) -> str:
        """
        Get the agent name.
        
        Returns:
            Agent name string
        """
        return "Developer"
    
    @property
    def agent_type(self) -> EAgent:
        """
        Get the agent type enum.
        
        Returns:
            EAgent enum value
        """
        return EAgent.Developer
    
    @property
    def project(self) -> Project:
        """
        Get the current project.
        
        Returns:
            Project object
        """
        return self._project
    
    @property
    def session(self):
        """
        Get the current session.
        
        Returns:
            Projses session object
        """
        return self._session

