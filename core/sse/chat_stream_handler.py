# --- core/sse/chat_stream_handler.py
import asyncio
from starlette.responses import Response, StreamingResponse

chat_stream_subscribers = {}



async def sse_chat_stream(request):
    session_key = request.cookies.get("sessionid")
    if not session_key:
        return Response("Missing session cookie", status_code=400)

    queue = asyncio.Queue()
    chat_stream_subscribers[session_key] = queue

    async def event_generator():
        try:
            while True:
                html = await queue.get()
                html_inline = html.replace("\n", "")
                print("[SSE INLINE DATA]", repr(html_inline))
                yield f"event: chat\ndata: {html_inline}\n\n"
        finally:
            chat_stream_subscribers.pop(session_key, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

