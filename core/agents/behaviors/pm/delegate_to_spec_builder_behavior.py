from core.agents.interfaces import AgentBehavior
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.session_state import SessionState


class DelegateToSpecBuilderBehavior(AgentBehavior):
    intent = {
        "start_spec",
        "edit_spec",
        "add_to_spec",
        "ask_a_question",
        "change_spec",
        "finalize_spec",
        "spec"
    }

    async def run(self, agent, content: str, intent) -> list:
        if intent.intent not in self.intent:
            return []

        # Signal to the ChatService that the agent should be switched to "Spec".
        session_change = SessionState(agent_name="Spec")

        return [
            ChatMessage(
                sender=agent.name,
                content="I am handing you over to the Specification Builder agent to work on the project requirements."
            ),
            ChatMessage(
                sender="Spec",
                content="Hello! I am the Specification Builder agent. How can I help you define the requirements for this project?"
            ),
            session_change
        ]
