from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent


class AskAQuestionBehavior(AgentBehavior):
    intent = ["ask_a_question", "query", "ask", "inquire", "question", "interrogate", "probe", "request_info"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return AgentMessage(
                sender=agent.name,
                text=llm_response.response,
            )
