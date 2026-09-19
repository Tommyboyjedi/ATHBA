from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
from llm_service.enums.eagent import EAgent


class IAgent(Protocol):
    async def run(self, content: str, request=None):
        ...

    def report(self) -> dict:
        ...

    @property
    def name(self) -> str:
        ...

    @property
    def llm_prompt(self) -> str:
        ...

    @property
    def agent_type(self) -> EAgent:
        ...

    @property
    def session(self):
        ...


@dataclass(frozen=True)
class BehaviorExecution:
    agent: IAgent
    message: str
    intent: LlmIntent


class AgentBehavior(Protocol):
    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        ...
