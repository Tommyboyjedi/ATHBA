import json
import logging
from django.template.loader import render_to_string
from core.agents.agent_generator import AgentGenerator
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.session_state import SessionState
from core.datastore.repos.conversation_repo import ConversationRepo
from core.services.session_proxy import SessionProxy
from core.sse.chat_stream_handler import chat_stream_subscribers
from django.utils.html import escape

log = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        self.repo = ConversationRepo()

    async def handle_user_message(self, request, session_key: str, user_input: str):
        project_id = request.session.get('project_id')

        if not project_id:
            log.debug("No active project, asking to create one.")
            response_msg = ChatMessage(sender="assistant", content="Welcome! This application requires at least one project to function initially. Would you like to create one now? (yes/no)")
            await self._stream(session_key, response_msg)
            return

        # 1. Save the user's message with full context
        user_msg = ChatMessage(
            sender="user",
            content=user_input,
            session_id=session_key,
            project_id=project_id
        )
        await self.repo.append_message(user_msg)

        # 2. Get agent based on session state
        agent_name = request.session.get('agent_name', 'PM')
        session_proxy = SessionProxy(request)
        agent = AgentGenerator().get_agent(agent_name, project_id, session_key, session_proxy)

        # 3. Run the agent and process its responses
        responses = await agent.run(user_input)

        # Collect zero or more agent switches requested by agents this turn
        switch_queue: list[str] = []

        def _ingest_messages(msgs):
            nonlocal switch_queue
            for msg in msgs:
                if isinstance(msg, ChatMessage):
                    # Ensure agent messages also have the correct session/project context
                    msg.session_id = session_key
                    msg.project_id = project_id
                    # Persist + stream
                    # (persisting assistant messages keeps full conversation history)
                    self.repo.append_message(msg)
                    # repo.append_message is async; ensure we await when called from async context
                elif isinstance(msg, SessionState):
                    if msg.agent_name:
                        # Update session to reflect the latest active agent (persist immediately)
                        session_proxy.set('agent_name', msg.agent_name)
                        switch_queue.append(msg.agent_name)

        # Ingest initial agent responses
        for msg in responses:
            if isinstance(msg, ChatMessage):
                msg.session_id = session_key
                msg.project_id = project_id
                await self.repo.append_message(msg)
                await self._stream(session_key, msg)
            elif isinstance(msg, SessionState):
                if msg.agent_name:
                    session_proxy.set('agent_name', msg.agent_name)
                    switch_queue.append(msg.agent_name)

        # Process routing queue breadth-first for this turn
        processed = set()
        while switch_queue:
            next_agent_name = switch_queue.pop(0)
            if next_agent_name in processed:
                continue
            processed.add(next_agent_name)

            routed_agent = AgentGenerator().get_agent(next_agent_name, project_id, session_key, session_proxy)
            routed_responses = await routed_agent.run(user_input)

            for msg in routed_responses:
                if isinstance(msg, ChatMessage):
                    msg.session_id = session_key
                    msg.project_id = project_id
                    await self.repo.append_message(msg)
                    await self._stream(session_key, msg)
                elif isinstance(msg, SessionState):
                    if msg.agent_name:
                        session_proxy.set('agent_name', msg.agent_name)
                        if msg.agent_name not in processed:
                            switch_queue.append(msg.agent_name)

    async def _stream(self, session_key: str, message: ChatMessage):
        if session_key in chat_stream_subscribers:
            html = render_to_string("partials/chat_message.html", {"msg": message}).strip()
            # Ensure message is on a single line for SSE
            await chat_stream_subscribers[session_key].put(html.replace("\n", ""))
        else:
            log.warning(f"STREAM: No SSE subscriber found for session_key: {session_key}")
