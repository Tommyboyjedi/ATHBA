from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class BasicReplyBehavior(AgentBehavior):
    intent = ["basic_reply"]

    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        if llm_response.intent not in self.intent:
            return None

        response_text = llm_response.response if llm_response.response else "I'm the Architect agent. I help analyze specifications and create development tickets. Ask me to analyze a specification to get started!"

        return [ChatMessage(
            sender=agent.name,
            content=response_text
        )]

