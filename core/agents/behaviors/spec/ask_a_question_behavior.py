from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage


class AskAQuestionBehavior:
    intent = ["ask_a_question", "query", "ask", "inquire", "question", "interrogate", "probe", "request_info"]

    async def run(self, execution: BehaviorExecution) -> list[ChatMessage] | None:
        llm_response = execution.intent
        if llm_response.intent not in self.intent:
            return None
        return [ChatMessage(sender=execution.agent.name, content=llm_response.response)]
