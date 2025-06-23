import json
from django.template.loader import render_to_string
from core.agents.agent_generator import AgentGenerator
from core.dataclasses.chat_message import ChatMessage
from core.datastore.repos.conversation_repo import ConversationRepo
from core.sse.chat_stream_handler import chat_stream_subscribers
from django.utils.html import escape

class ChatService:
    def __init__(self):
        self.repo = ConversationRepo()

    async def handle_user_message(self, session, user_input: str):
        user_msg = ChatMessage(sender="user", content=user_input).with_session(session)
        await self.repo.append_message(user_msg)

        agent = AgentGenerator().get_agent(session)
        responses = await agent.run(user_input)

        for msg in responses:
            if isinstance(msg, ChatMessage):
                msg.with_session(session)
                await self.repo.append_message(msg)
                await self._stream(session.session_id, msg)

    # async def _stream(self, session_id: str, message: ChatMessage):
    #     if session_id in chat_stream_subscribers:
    #         html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
    #         print("HTML OUTPUT TO STREAM:", repr(html))
    #         print("HTML with replace:", html.replace("\n", ""))
    #         await chat_stream_subscribers[session_id].put(html.replace("\n", ""))


    async def _stream(self, session_id: str, message: ChatMessage):
        if session_id in chat_stream_subscribers:
            html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
            if not message.metadata == None:
                html += """
                <template hx-swap-oob="innerHTML:#main-panel">
                  <div hx-get="/api/ui/overview/" hx-trigger="load" hx-target="#main-panel" hx-swap="innerHTML">Refreshing overview…</div>
                </template>
                """

            await chat_stream_subscribers[session_id].put(html.replace("\n", ""))



