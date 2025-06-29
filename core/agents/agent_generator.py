import base64
import json
from core.dataclasses.projses import Projses


class AgentGenerator:

    def get_agent(self, session_key: str):
        try:
            # Django session key is <session_data>:<salt>:<signature>
            # session_data is base64 encoded JSON
            session_data_b64 = session_key.split(':')[0]
            # Pad the base64 string if needed
            session_data_json = base64.urlsafe_b64decode(
                session_data_b64 + '=' * (-len(session_data_b64) % 4)
            ).decode('utf-8')
            session_data = json.loads(session_data_json)
            agent_name = session_data.get('agent_name')
            project_id = session_data.get('project_id')

            # The agents expect a session object, not just the key.
            # We'll create a Projses object from the parsed key.
            session = Projses(
                session_id=session_key,
                project_id=project_id,
                agent_name=agent_name
            )
        except Exception:
            # If parsing fails, we cannot determine the agent.
            return None

        if session.agent_name == "PM":
            from core.agents.pm_agent import PmAgent
            return PmAgent(session)
        if session.agent_name == "Spec":
            from core.agents.spec_agent import SpecBuilderAgent
            return SpecBuilderAgent(session)