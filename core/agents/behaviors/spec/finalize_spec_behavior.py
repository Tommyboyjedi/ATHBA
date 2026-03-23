from core.agents.interfaces import AgentBehavior
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent
import asyncio


class FinalizeSpecBehavior(AgentBehavior):
    intent = ["finalize_spec"]

    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> list[ChatMessage] | None:
        if llm_response.intent not in self.intent:
            return None

        # Get the latest spec version
        from core.datastore.repos.spec_version_repo import SpecVersionRepo
        spec_repo = SpecVersionRepo()
        
        spec_versions = await spec_repo.find(
            {"project_id": agent.session.project_id},
            sort=[("version", -1)],
            limit=1
        )
        
        if not spec_versions:
            return [ChatMessage(
                sender=agent.name,
                content="❌ No specification found to finalize. Please create a specification first."
            )]
        
        latest_spec = spec_versions[0]
        version = latest_spec.get("version", 1)

        # Mark the spec as approved (add approval metadata)
        await spec_repo.update(
            {"project_id": agent.session.project_id, "version": version},
            {"approved": True, "approved_by": "human", "approved_at": latest_spec.get("created_at")}
        )

        # Launch Architect agent asynchronously to analyze spec and create tickets
        asyncio.create_task(self._run_architect(agent.session))

        return [
            ChatMessage(
                sender=agent.name,
                content=f"✅ Specification v{version} has been finalized and approved! Routing to the Architect to generate development tickets..."
            )
        ]

    async def _run_architect(self, session):
        """Run the Architect agent to analyze the spec and generate tickets."""
        from core.agents.architect_agent import ArchitectAgent
        from core.sse.chat_stream_handler import chat_stream_subscribers
        from django.template.loader import render_to_string
        
        # Create architect agent with cloned session
        architect_session = session.clone()
        architect_session.agent_name = "Architect"
        architect = ArchitectAgent(architect_session)
        await architect.initialize()
        
        # Run the architect with the analyze_spec command
        responses = await architect.run("analyze the approved specification and create development tickets")
        
        # Stream responses back to the chat
        for msg in responses:
            if isinstance(msg, ChatMessage):
                msg.with_session(session)
                # Stream to SSE if subscriber exists
                if session.session_id in chat_stream_subscribers:
                    html = render_to_string("partials/chat_message.html", {"msg": msg}).strip()
                    await chat_stream_subscribers[session.session_id].put(html.replace("\n", ""))

