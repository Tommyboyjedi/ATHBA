"""Chat service for handling user messages and streaming responses."""

import logging
from typing import List

from django.template.loader import render_to_string

from core.agents.agent_generator import AgentGenerator
from core.dataclasses.chat_message import ChatMessage
from core.datastore.repos.conversation_repo import ConversationRepo
from core.services.service_requests import ChatMessageRequest
from core.sse.chat_stream_handler import chat_stream_subscribers

log = logging.getLogger(__name__)


class ChatService:
    def __init__(self):
        self.repo = ConversationRepo()

    async def handle_user_message(self, chat_request_or_request, *args) -> None:
        if isinstance(chat_request_or_request, ChatMessageRequest):
            chat_request = chat_request_or_request
        else:
            chat_request = ChatMessageRequest(
                request=chat_request_or_request,
                session_key=args[0],
                user_input=args[1],
            )
        try:
            user_msg = ChatMessage(sender="user", content=chat_request.user_input).with_session_key(chat_request.session_key)
            await self.repo.append_message(user_msg)
            await self._send_typing_indicator(chat_request.session_key, True)
            agent = AgentGenerator().get_agent(chat_request.session_key)
            responses = await agent.run(chat_request.user_input, chat_request.request)
            for msg in responses:
                if not isinstance(msg, ChatMessage):
                    continue
                msg.with_session_key(chat_request.session_key)
                await self.repo.append_message(msg)
                await self._stream(chat_request.session_key, msg)
            await self._send_typing_indicator(chat_request.session_key, False)
        except Exception as error:
            log.error(f"Error handling user message: {error}", exc_info=True)
            error_msg = ChatMessage(
                sender="system",
                content=f"Error processing your message: {error}",
                metadata={"is_error": True},
            ).with_session_key(chat_request.session_key)
            await self._stream(chat_request.session_key, error_msg)
            await self._send_typing_indicator(chat_request.session_key, False)
            raise

    async def _stream(self, session_key: str, message: ChatMessage) -> None:
        if session_key in chat_stream_subscribers:
            html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
            await chat_stream_subscribers[session_key].put(html.replace("\n", ""))
        else:
            log.warning(f"STREAM: No SSE subscriber found for session_key: {session_key}")

    async def _send_typing_indicator(self, session_key: str, is_typing: bool) -> None:
        if session_key in chat_stream_subscribers:
            display = "block" if is_typing else "none"
            indicator_html = (
                f'<div id="typing-indicator" class="typing-indicator" '
                f'style="display: {display};">'
                f'Agent is thinking<span class="dots">...</span></div>'
            )
            await chat_stream_subscribers[session_key].put(indicator_html)

    async def get_conversation_history(self, session_key: str, limit: int = 50) -> List[dict]:
        try:
            return await self.repo.get_recent(session_key, limit)
        except Exception as error:
            log.error(f"Error retrieving conversation history: {error}", exc_info=True)
            return []

    async def clear_conversation_history(self, session_key: str) -> None:
        try:
            await self.repo.clear_conversation(session_key)
            log.info(f"Cleared conversation history for session: {session_key}")
        except Exception as error:
            log.error(f"Error clearing conversation history: {error}", exc_info=True)
            raise
