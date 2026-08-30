import asyncio

from core.agents.architect_agent import ArchitectAgent
from core.agents.interfaces import BehaviorExecution
from core.dataclasses.chat_message import ChatMessage
from core.dataclasses.llm_intent import LlmIntent


class FinalizeSpecBehavior:
    intent = ["finalize_spec"]

    async def run(self, execution_or_agent, *args) -> list[ChatMessage] | None:
        execution = execution_or_agent
        if not isinstance(execution, BehaviorExecution):
            execution = BehaviorExecution(agent=execution_or_agent, message=args[0], intent=args[1])
        agent = execution.agent
        user_input = execution.message
        llm_response = execution.intent

        if llm_response.intent not in self.intent:
            return None

        spec_versions = await agent.spec_repo.find(
            {"project_id": agent.session.project_id},
            sort=[("version", -1)],
            limit=1,
        )

        if not spec_versions:
            return [
                ChatMessage(
                    sender=agent.name,
                    content="❌ No specification found to finalize. Please create a specification first.",
                )
            ]

        latest_spec = spec_versions[0]
        version = latest_spec.get("version", 1)

        await agent.spec_repo.update(
            {"project_id": agent.session.project_id, "version": version},
            {
                "approved": True,
                "approved_by": "human",
                "approved_at": latest_spec.get("created_at"),
            },
        )

        asyncio.create_task(self._run_architect(agent.session))

        return [
            ChatMessage(
                sender=agent.name,
                content=f"✅ Specification v{version} has been finalized and approved! Routing to the Architect to generate development tickets...",
            )
        ]

    async def _run_architect(self, session):
        from core.sse.chat_stream_handler import chat_stream_subscribers
        from django.template.loader import render_to_string

        architect_session = session.clone()
        architect_session.agent_name = "Architect"
        architect = ArchitectAgent(architect_session)
        await architect.initialize()

        responses = await architect.run("analyze the approved specification and create development tickets")

        for msg in responses:
            if isinstance(msg, ChatMessage):
                msg.with_session(session)
                if session.session_id in chat_stream_subscribers:
                    html = render_to_string("partials/chat_message.html", {"msg": msg}).strip()
                    await chat_stream_subscribers[session.session_id].put(html.replace("\n", ""))
