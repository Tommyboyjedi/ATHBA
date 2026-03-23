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
        """Handle a user message with error handling and status updates"""
        try:
            # 1. Save the user's message (but don't stream it back)
            user_msg = ChatMessage(sender="user", content=user_input).with_session_key(session_key)
            await self.repo.append_message(user_msg)
            # The user's message is now rendered client-side optimistically.

            # 2. Send typing indicator
            await self._send_typing_indicator(session_key, True)

            # 3. Run the agent and stream its responses
            agent = AgentGenerator().get_agent(session_key)
            responses = await agent.run(user_input, request)

            for msg in responses:
                if isinstance(msg, ChatMessage):
                    msg.with_session_key(session_key)
                    await self.repo.append_message(msg)
                    await self._stream(session_key, msg)
            
            # 4. Remove typing indicator
            await self._send_typing_indicator(session_key, False)
            
        except Exception as e:
            log.error(f"Error handling user message: {e}", exc_info=True)
            # Send error message to chat
            error_msg = ChatMessage(
                sender="system",
                content=f"Error processing your message: {str(e)}",
                metadata={"is_error": True}
            ).with_session_key(session_key)
            await self._stream(session_key, error_msg)
            await self._send_typing_indicator(session_key, False)
            raise

    async def _stream(self, session_key: str, message: ChatMessage):
        """Stream a message to the client"""
        if session_key in chat_stream_subscribers:
            html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
            # Ensure message is on a single line for SSE
            await chat_stream_subscribers[session_key].put(html.replace("\n", ""))
        else:
            log.warning(f"STREAM: No SSE subscriber found for session_key: {session_key}")
    
    async def _send_typing_indicator(self, session_key: str, is_typing: bool):
        """Send typing indicator status to the client"""
        if session_key in chat_stream_subscribers:
            indicator_html = f'<div id="typing-indicator" class="typing-indicator" style="display: {"block" if is_typing else "none"};">Agent is thinking<span class="dots">...</span></div>'
            await chat_stream_subscribers[session_key].put(indicator_html)
    
    async def get_conversation_history(self, session_key: str, limit: int = 50):
        """Retrieve conversation history for a session"""
        try:
            messages = await self.repo.get_recent(session_key, limit)
            return messages
        except Exception as e:
            log.error(f"Error retrieving conversation history: {e}", exc_info=True)
            return []
    
    async def clear_conversation_history(self, session_key: str):
        """Clear conversation history for a session"""
        try:
            await self.repo.clear_conversation(session_key)
            log.info(f"Cleared conversation history for session: {session_key}")
        except Exception as e:
            log.error(f"Error clearing conversation history: {e}", exc_info=True)
            raise
