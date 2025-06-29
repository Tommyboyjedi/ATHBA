from core.agents.interfaces import AgentBehavior
from core.dataclasses.llm_intent import LlmIntent
from core.agents.pm_agent import PmAgent
from core.dataclasses.chat_message import ChatMessage


class ConfirmActionBehavior(AgentBehavior):
    intent = "confirm_action"

    async def run(self, agent: PmAgent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage]:
        if llm_response.intent != self.intent:
            return []

        pending_action = agent.request.session.get('pending_action')
        if not pending_action:
            return []

        confirmation = llm_response.entities.get('confirmation', 'no').lower()
        is_confirmed = confirmation == 'yes'

        action_type = pending_action.get('type')
        project_id = pending_action.get('project_id')
        project_name = pending_action.get('project_name')

        # Clear the pending action from the session
        del agent.request.session['pending_action']

        if action_type == 'activate_project':
            if is_confirmed:
                agent.request.session['project_id'] = project_id
                agent.request.session.save()
                content = f"OK. I've made '{project_name}' the active project."
                return [ChatMessage(
                    sender=agent.name,
                    content=content,
                    metadata={"refresh_overview": True}
                )]
            else:
                content = f"OK. I will not activate '{project_name}'."
                return [ChatMessage(
                    sender=agent.name,
                    content=content
                )]

        return []
