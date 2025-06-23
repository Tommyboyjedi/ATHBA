# import json
#
# from django.shortcuts import render
# from ninja import Router, Form
# from ninja.responses import Response
#
# from core.services.chat_service import ChatService
# from core.services.session_service import SessionService
#
#
# chat_router = Router()
#
# from sse_starlette.sse import EventSourceResponse
# import asyncio
#
# chat_stream_subscribers = {}
#
# @chat_router.get("/stream")
# async def stream_messages(request):
#     session_id = request.session.get("session_id")
#     if session_id is None:
#         return Response("Missing session_id", status=400)
#
#     queue = asyncio.Queue()
#     chat_stream_subscribers[session_id] = queue
#
#     async def event_generator():
#         try:
#             while True:
#                 data = await queue.get()
#                 yield {"event": "chat", "data": data}
#         finally:
#             chat_stream_subscribers.pop(session_id, None)
#
#     return EventSourceResponse(event_generator())
#
# @chat_router.post("send")
# async def send_message(request, message: str = Form(...)):
#     session = await SessionService().manage(request)
#     await ChatService().process_message(session, message)
#     return Response("""
#     <script>
#       const el = document.querySelector('#chat-stream');
#       if (el) {
#         el.setAttribute('sse-connect', '/chat/stream/');
#         htmx.process(el);
#       }
#     </script>
#     """)
