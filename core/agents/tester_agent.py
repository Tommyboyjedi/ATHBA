"""
Tester Agent module.

This module implements the Tester Agent, which is responsible for
enforcing TDD by writing tests first, executing tests, and verifying
code quality before approval.
"""

from core.agents.behaviors.behavior_loader import BehaviorLoader
from core.agents.helpers.llm_exchange import LlmExchange
from core.agents.interfaces import IAgent
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.project import Project
from core.dataclasses.projses import Projses
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.project_service import ProjectsService
from core.services.git_service import GitService
from core.services.test_execution_service import TestExecutionService
from core.services.llm_escalation_manager import LlmEscalationManager
from llm_service.enums.eagent import EAgent


class TesterAgent(IAgent):
    """
    Tester Agent for TDD enforcement and code quality verification.
    
    The Tester Agent is responsible for:
    - Claiming tickets from the Review column
    - Analyzing code changes on branches
    - Generating tests BEFORE implementation (TDD RED phase)
    - Executing tests with pytest
    - Verifying code passes tests (TDD GREEN phase)
    - Approving or rejecting code
    - LLM escalation on repeated failures
    
    Attributes:
        name: Agent name ("Tester")
        session: Current session (Projses object)
        ticket_repo: Repository for ticket operations
        git_service: Service for Git operations
        test_service: Service for test execution
        escalation_manager: Manager for LLM tier escalation
        behaviors: List of loaded behaviors
    """
    
    def __init__(self, session: Projses):
        """
        Initialize the Tester Agent.
        
        Args:
            session: Session object containing project_id and agent_name
        """
        self._session = session
        self._session.agent_name = self.name
        self.ticket_repo = TicketRepo()
        self.git_service = GitService()
        self.test_service = TestExecutionService()
        self.escalation_manager = LlmEscalationManager()
        self.behaviors = BehaviorLoader().load_for_agent(self)
    
    async def initialize(self):
        """
        Initialize the agent by loading project data.
        """
        self._project = await ProjectsService().get_project_by_id(self._session.project_id)
    
    async def run(self, content: str) -> list[ChatMessage]:
        """
        Process user input and execute appropriate behaviors.
        
        Uses local LLM with escalation support for test generation.
        
        Args:
            content: User input message
            
        Returns:
            List of ChatMessage responses from behaviors
        """
        # Tester uses local LLM by default with escalation
        # Get current tier if working on a ticket
        tier = None
        if hasattr(self._session, 'current_ticket') and self._session.current_ticket:
            ticket = await self.ticket_repo.get_ticket_by_id(self._session.current_ticket)
            if ticket:
                tier = self.escalation_manager.get_current_tier(ticket, "Tester")
        
        response = await LlmExchange(
            agent=self,
            session=self._session,
            content=content,
            tier=tier,  # Use escalated tier if available
            use_cloud=False  # Use local LLM for Tester
        ).get_intent()
        
        result_messages = []
        for behavior in self.behaviors:
            messages = await behavior.run(self, content, response)
            if messages:
                if isinstance(messages, list):
                    result_messages.extend(messages)
                else:
                    result_messages.append(messages)
        
        return result_messages
    
    @property
    def name(self) -> str:
        """Agent name."""
        return "Tester"
    
    @property
    def agent_type(self) -> EAgent:
        """Agent type enum."""
        return EAgent.Tester
    
    @property
    def project(self) -> Project:
        """Current project."""
        return self._project
    
    @property
    def session(self) -> Projses:
        """Current session."""
        return self._session
    
    @property
    def llm_prompt(self) -> str:
        """
        LLM system prompt for the Tester agent.
        
        Returns:
            System prompt string for intent detection
        """
        return """You are a Tester Agent in an AI development team following strict TDD principles.

Your responsibilities:
- Write tests BEFORE implementation (TDD RED phase)
- Execute tests to verify code quality
- Approve code that passes all tests
- Reject code that fails tests with detailed feedback
- Follow Uncle Bob's TDD rules strictly

Available behaviors:
- claim_review: Claim a ticket from Review column for testing
- analyze_code: Analyze code changes on a branch
- generate_test: Generate a failing test (TDD RED phase)
- execute_tests: Run pytest and get results
- verify_pass: Verify all tests pass (TDD GREEN phase)
- approve_code: Approve code and move ticket to Done
- reject_code: Reject code and return to Developer
- basic_reply: Answer questions or provide status

User message: """
