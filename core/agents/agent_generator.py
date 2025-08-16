from core.dataclasses.projses import Projses
from core.services.session_proxy import SessionProxy


class AgentGenerator:

    def get_agent(self, agent_name: str, project_id: str, session_key: str, session_proxy: SessionProxy):
        # The agents expect a session object, which we create from the provided data.
        session = Projses(
            session_id=session_key,
            project_id=project_id,
            agent_name=agent_name
        )

        if session.agent_name == "PM":
            from core.agents.pm_agent import PmAgent
            return PmAgent(session, session_proxy)

        if session.agent_name == "Spec":
            from core.agents.spec_agent import SpecBuilderAgent
            return SpecBuilderAgent(session)

        # Fallback to PM agent if agent_name is unknown or None
        from core.agents.pm_agent import PmAgent
        return PmAgent(session, session_proxy)