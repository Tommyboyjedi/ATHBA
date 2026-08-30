from core.agents.interfaces import BehaviorExecution
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent


class AskAQuestionBehavior:
    intent = ["ask_a_question", "query", "ask", "inquire", "question", "interrogate", "probe", "request_info"]

    async def run(self, execution: BehaviorExecution) -> AgentMessage | None:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent not in self.intent:
            return AgentMessage(
                sender=agent.name,
                text=llm_response.response,
            )
