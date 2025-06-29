import asyncio
import logging
from starlette.responses import Response, StreamingResponse

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

chat_stream_subscribers = {}


async def sse_chat_stream(request):
    session_key = request.query_params.get("session")
    if not session_key:
        log.error("SSE: Session key missing from query parameters.")
        return Response("Missing session key in query parameters", status_code=400)

    queue = asyncio.Queue()
    chat_stream_subscribers[session_key] = queue

    async def event_generator():
        log.debug(f"SSE: Connection opened and event generator started for session: {session_key}")
        try:
            yield ":open\n\n"
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: chat\ndata: {message}\n\n"
                    queue.task_done()
                except asyncio.TimeoutError:
                    # This is a normal event, used to keep the connection alive.
                    yield ":keepalive\n\n"
        except Exception as e:
            log.error(f"SSE: Exception in event generator for {session_key}: {e}", exc_info=True)
        finally:
            log.debug(f"SSE: Cleaning up subscriber for session: {session_key}")
            if session_key in chat_stream_subscribers:
                del chat_stream_subscribers[session_key]

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), headers=headers)