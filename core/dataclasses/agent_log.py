from dataclasses import dataclass
from datetime import datetime

from core.dataclasses.project import Project


@dataclass
class AgentLog:
    project: Project
    agent: str
    event: str
    timestamp: datetime

    def __str__(self):
        return f"{self.timestamp}: {self.agent} - {self.event[:50]}"
