from core.dataclasses.projses import Projses


class AgentGenerator:

    def get_agent(self, session: Projses):

        if session.agent_name == "PM":
            from core.agents.pm_agent import PmAgent
            return PmAgent(session)
        if session.agent_name == "Spec":
            from core.agents.spec_agent import SpecBuilderAgent
            return SpecBuilderAgent(session)