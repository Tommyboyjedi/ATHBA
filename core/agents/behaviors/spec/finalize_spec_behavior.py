from core.agents.interfaces import AgentBehavior
from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent


class FinalizeSpecBehavior(AgentBehavior):
    intent = ["finalize_spec"]

    async def run(self, agent: SpecBuilderAgent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
        if llm_response.intent not in self.intent:
            return None

        return AgentMessage(
            sender=agent.agent_id,
            text="✅ This is a stub for FinalizeSpecBehavior responding to intent 'finalize_spec'."
        )
