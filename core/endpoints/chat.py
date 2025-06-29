#core/endpoints/chat.py

from core.services.chat_service import ChatService
from ninja import Router, Form
from ninja.responses import Response

chat_router = Router()

@chat_router.post("send")
async def send_message(request, message: str = Form(...), session_key: str = Form(...)):
    await ChatService().handle_user_message(session_key, message)

    return Response("""
    <script>
      const el = document.querySelector('#chat-stream');
      if (el && el.hasAttribute('sse-connect')) {
        el.removeAttribute('sse-connect');
        htmx.process(el);
      }
    </script>
    """)
