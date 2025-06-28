# --- core/sse/chat_stream_handler.py
import asyncio
from starlette.responses import Response, StreamingResponse

chat_stream_subscribers = {}


async def sse_chat_stream(request):
    session_key = request.cookies.get("sessionid")
    if not session_key:
        return Response("Missing session cookie", status_code=400)

    # Create a new queue for this connection
    queue = asyncio.Queue()
    chat_stream_subscribers[session_key] = queue

    # Send initial message to confirm connection
    await queue.put("<div>SSE Connection Established</div>")

    async def event_generator():
        try:
            # Send initial connection confirmation
            yield ":open\n\n"

            while True:
                try:
                    # Get the next message (with timeout to allow keep-alive)
                    message = await asyncio.wait_for(queue.get(), timeout=30)

                    # Format as SSE message
                    yield f"event: chat\ndata: {message}\n\n"

                    # Mark the task as done
                    queue.task_done()

                except asyncio.TimeoutError:
                    # Send keep-alive comment
                    yield ":keepalive\n\n"
        except Exception as e:
            print(f"Error in SSE stream: {e}")
        finally:
            # Clean up
            chat_stream_subscribers.pop(session_key, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )