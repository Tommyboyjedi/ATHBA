from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage


class BasicReplyBehavior:
    intent = ["basic_reply"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage]:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent in self.intent:
            # Always returns the raw LLM response if no other behavior has matched
            return [
                ChatMessage(
                    sender=agent.name,
                    content=llm_response.response.strip()
                )
            ]
        return []
