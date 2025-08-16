import json
import logging
from django.template.loader import render_to_string
from core.agents.agent_generator import AgentGenerator
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.session_state import SessionState
from core.datastore.repos.conversation_repo import ConversationRepo
from core.services.session_proxy import SessionProxy
from core.sse.chat_stream_handler import chat_stream_subscribers
from django.utils.html import escape

log = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.repo = ConversationRepo()

    async def handle_user_message(self, request, session_key: str, user_input: str):
        project_id = request.session.get('project_id')

        if not project_id:
            log.debug("No active project, asking to create one.")
            response_msg = ChatMessage(sender="assistant", content="Welcome! This application requires at least one project to function initially. Would you like to create one now? (yes/no)")
            await self._stream(session_key, response_msg)
            return

        # 1. Save the user's message with full context
        user_msg = ChatMessage(
            sender="user",
            content=user_input,
            session_id=session_key,
            project_id=project_id
        )
        await self.repo.append_message(user_msg)

        # 2. Get agent based on session state
        agent_name = request.session.get('agent_name', 'PM')
        session_proxy = SessionProxy(request)
        agent = AgentGenerator().get_agent(agent_name, project_id, session_key, session_proxy)

        # 3. Run the agent and process its responses
        responses = await agent.run(user_input)

        for msg in responses:
            if isinstance(msg, ChatMessage):
                # Ensure agent messages also have the correct session/project context
                msg.session_id = session_key
                msg.project_id = project_id
                await self.repo.append_message(msg)
                await self._stream(session_key, msg)
            elif isinstance(msg, SessionState):
                # The agent has requested a change to the session state
                if msg.agent_name:
                    request.session['agent_name'] = msg.agent_name

    async def _stream(self, session_key: str, message: ChatMessage):
        if session_key in chat_stream_subscribers:
            html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
            # Ensure message is on a single line for SSE
            await chat_stream_subscribers[session_key].put(html.replace("\n", ""))
        else:
            log.warning(f"STREAM: No SSE subscriber found for session_key: {session_key}")
