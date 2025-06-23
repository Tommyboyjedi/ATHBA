import copy
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class Projses:
    session_id: str
    project_id: str
    agent_name: str

    # def clone(self, **overrides) -> "Projses":
    #     data = copy.deepcopy(asdict(self))
    #     data.update(overrides)
    #     return Projses(**data)

    def clone(self) -> "Projses":
        return Projses(
            session_id=self.session_id,
            project_id=self.project_id,
            agent_name=self.agent_name
        )
