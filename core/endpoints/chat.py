#core/endpoints/chat.py

from core.services.chat_service import ChatService
from ninja import Router, Form
from ninja.responses import Response
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
