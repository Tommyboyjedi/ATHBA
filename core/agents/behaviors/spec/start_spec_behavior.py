from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage


class StartSpecBehavior:
    intent = [
        "start_spec",
        "begin_spec",
        "commence_spec",
        "initiate_spec",
        "launch_spec",
        "start",
        "begin",
        "commence",
        "initiate",
        "launch",
    ]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        llm_response = execution.intent
        if llm_response.intent not in self.intent:
            return None
        content = llm_response.response or (
            "🧱 I've created the initial structure for the project specification. "
            "Please describe your first requirement."
        )
        return [ChatMessage(sender=execution.agent.name, content=content)]
