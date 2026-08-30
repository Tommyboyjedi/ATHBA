from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage


class ChangeSpecBehavior:
    intent = ["change_spec"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        llm_response = execution.intent
        if llm_response.intent not in self.intent:
            return None
        content = llm_response.response or (
            "✅ This is a stub for ChangeSpecBehavior responding to intent 'change_spec'."
        )
        return [ChatMessage(sender=execution.agent.name, content=content)]
