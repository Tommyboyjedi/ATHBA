from core.agents.interfaces import BehaviorExecution
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent


class ChangeSpecBehavior:
    intent = ["change_spec"]

    async def run(self, execution: BehaviorExecution) -> AgentMessage | None:
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent not in self.intent:
            return None

        return AgentMessage(
            sender=agent.agent_id,
            text="✅ This is a stub for ChangeSpecBehavior responding to intent 'change_spec'."
        )
