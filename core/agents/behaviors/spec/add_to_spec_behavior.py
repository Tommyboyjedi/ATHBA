from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage


class AddToSpecBehavior:
    intent = ["add_to_spec"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        llm_response = execution.intent
        if llm_response.intent not in self.intent:
            return None
        content = llm_response.response or (
            "📌 I've added your new requirement to the current specification draft."
        )
        return [ChatMessage(sender=execution.agent.name, content=content)]
