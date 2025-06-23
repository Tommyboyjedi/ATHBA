from abc import ABC, abstractmethod
from typing import List

from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent
from llm_service.enums.eagent import EAgent


class IAgent(ABC):
    @abstractmethod
    def run(self, content: str):
        pass

    @abstractmethod
    def report(self) -> dict:
        pass


    @property
    @abstractmethod
    def name(self) -> str:
        """
        The name of the agent.
        """
        pass

    @property
    @abstractmethod
    def llm_prompt(self) -> str:
        """
        The name of the agent.
        """
        pass

    @property
    @abstractmethod
    def agent_type(self) -> EAgent:
        pass

    @property
    @abstractmethod
    def session(self):
        """
        The session associated with the agent.
        """
        pass


class AgentBehavior(ABC):
    @abstractmethod
    async def run(self, agent: IAgent, message: str, intent: LlmIntent) -> bool:
        """
        Process the incoming message. If this behavior can handle it,
        return an AgentMessage. Otherwise, return None.
        """
        pass
