from core.agents.interfaces import AgentBehavior
from core.dataclasses.agent_message import AgentMessage
from core.dataclasses.llm_intent import LlmIntent


class FinalizeSpecBehavior(AgentBehavior):
    intent = ["finalize_spec"]

    async def run(self, agent, user_input: str, llm_response: LlmIntent) -> AgentMessage | None:
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
            return AgentMessage(
                sender=agent.name,
                text="❌ No specification found to finalize. Please create a specification first."
            )
        
        latest_spec = spec_versions[0]
        version = latest_spec.get("version", 1)

        # Mark the spec as approved (add approval metadata)
        await spec_repo.update(
            {"project_id": agent.session.project_id, "version": version},
            {"approved": True, "approved_by": "human", "approved_at": latest_spec.get("created_at")}
        )

        return [
            AgentMessage(
                sender=agent.name,
                text=f"✅ Specification v{version} has been finalized and approved! Routing to the Architect to generate development tickets..."
            ),
            AgentMessage(
                sender=agent.name,
                text="@Architect",
                routing=["Architect"]
            )
        ]
