from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class BasicReplyBehavior:
    intent = ["basic_reply"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent not in self.intent:
            return None

        response_text = llm_response.response if llm_response.response else "I'm the Architect agent. I help analyze specifications and create development tickets. Ask me to analyze a specification to get started!"

        return [ChatMessage(
            sender=agent.name,
            content=response_text
        )]

