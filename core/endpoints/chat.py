"""
Chat endpoints for handling user messages and conversation management.

This module provides REST API endpoints for:
- Sending messages
- Retrieving conversation history
- Clearing conversations

All endpoints follow the repository's error handling patterns with
try/catch blocks and user-friendly error messages.
"""
from core.services.chat_service import ChatService
from ninja import Router, Form
from ninja.responses import Response
from typing import Dict, Any
import logging

log = logging.getLogger(__name__)

chat_router = Router()


@chat_router.post("send")
async def send_message(
    request,
    message: str = Form(...),
    session_key: str = Form(...)
) -> Response:
    """
    Send a user message and trigger agent response.
    
    This endpoint:
    1. Validates the input
    2. Processes the message through ChatService
    3. Returns JavaScript to reconnect SSE if needed
    
    Args:
        request: Django request object
        message: User's message text
        session_key: Session identifier
        
    Returns:
        Response with JavaScript for SSE reconnection or error HTML
        
    Raises:
        400: If message is empty or session_key is missing
        500: If message processing fails
    """
    try:
        # Validate inputs
        if not message or not message.strip():
            return Response(
                """<div class="error-toast">Message cannot be empty</div>""",
                status=400
            )
        
        if not session_key:
            return Response(
                """<div class="error-toast">Invalid session</div>""",
                status=400
            )
        
        await ChatService().handle_user_message(request, session_key, message)

        return Response("""
        <script>
          const el = document.querySelector('#chat-stream');
          if (el && el.hasAttribute('sse-connect')) {
            el.removeAttribute('sse-connect');
            htmx.process(el);
          }
        </script>
        """)
    except Exception as e:
        log.error(f"Error in send_message: {e}", exc_info=True)
        return Response(
            """<div class="error-toast">Failed to send message. Please try again.</div>""",
            status=500
        )


@chat_router.get("history")
async def get_history(
    request,
    session_key: str,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Retrieve conversation history for a session.
    
    Args:
        request: Django request object
        session_key: Session identifier
        limit: Maximum number of messages to return (default: 50)
        
    Returns:
        JSON with messages array or error object
        
    Raises:
        500: If history retrieval fails
    """
    try:
        service = ChatService()
        messages = await service.get_conversation_history(session_key, limit)
        return {"messages": [msg.to_dict() for msg in messages]}
    except Exception as e:
        log.error(f"Error retrieving history: {e}", exc_info=True)
        return Response(
            {"error": "Failed to retrieve conversation history"},
            status=500
        )


@chat_router.post("clear")
async def clear_history(
    request,
    session_key: str = Form(...)
) -> Response:
    """
    Clear conversation history for a session.
    
    This endpoint clears all messages in the conversation and
    returns JavaScript to clear the UI.
    
    Args:
        request: Django request object
        session_key: Session identifier
        
    Returns:
        Response with JavaScript to clear chat UI or error HTML
        
    Raises:
        500: If clearing fails
    """
    try:
        service = ChatService()
        await service.clear_conversation_history(session_key)
        return Response("""
        <script>
          const chatStream = document.getElementById('chat-stream');
          if (chatStream) {
            // Clear all messages except typing indicator
            const messages = chatStream.querySelectorAll('.message');
            messages.forEach(msg => msg.remove());
          }
          showToast('Conversation cleared');
        </script>
        """)
    except Exception as e:
        log.error(f"Error clearing history: {e}", exc_info=True)
        return Response(
            """<div class="error-toast">Failed to clear conversation</div>""",
            status=500
        )
