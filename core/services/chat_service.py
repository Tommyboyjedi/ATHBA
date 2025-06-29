import json
import logging
from django.template.loader import render_to_string
from core.agents.agent_generator import AgentGenerator
from core.dataclasses.chat_message import ChatMessage
from core.datastore.repos.conversation_repo import ConversationRepo
from core.sse.chat_stream_handler import chat_stream_subscribers
from django.utils.html import escape

log = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.repo = ConversationRepo()

    async def handle_user_message(self, request, session_key: str, user_input: str):
        # 1. Save the user's message (but don't stream it back)
        user_msg = ChatMessage(sender="user", content=user_input).with_session_key(session_key)
        await self.repo.append_message(user_msg)
        # The user's message is now rendered client-side optimistically.

        # 2. Run the agent and stream its responses
        agent = AgentGenerator().get_agent(session_key)
        responses = await agent.run(user_input, request)

        for msg in responses:
            if isinstance(msg, ChatMessage):
                msg.with_session_key(session_key)
                await self.repo.append_message(msg)
                await self._stream(session_key, msg)

    async def _stream(self, session_key: str, message: ChatMessage):
        if session_key in chat_stream_subscribers:
            html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
            # Ensure message is on a single line for SSE
            await chat_stream_subscribers[session_key].put(html.replace("\n", ""))
        else:
            log.warning(f"STREAM: No SSE subscriber found for session_key: {session_key}")
