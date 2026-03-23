#core/endpoints/chat.py

from core.services.chat_service import ChatService
from ninja import Router, Form
from ninja.responses import Response
from typing import List, Optional
import logging

log = logging.getLogger(__name__)

chat_router = Router()

@chat_router.post("send")
async def send_message(request, message: str = Form(...), session_key: str = Form(...)):
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
            f"""<div class="error-toast">Failed to send message. Please try again.</div>""",
            status=500
        )

@chat_router.get("history")
async def get_history(request, session_key: str, limit: int = 50):
    """Get conversation history for a session"""
    try:
        service = ChatService()
        messages = await service.get_conversation_history(session_key, limit)
        return {"messages": [msg.to_dict() for msg in messages]}
    except Exception as e:
        log.error(f"Error retrieving history: {e}", exc_info=True)
        return Response({"error": "Failed to retrieve conversation history"}, status=500)

@chat_router.post("clear")
async def clear_history(request, session_key: str = Form(...)):
    """Clear conversation history for a session"""
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
