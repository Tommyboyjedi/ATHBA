from dataclasses import dataclass
from datetime import datetime

from core.dataclasses.project import Project


@dataclass
class CodeSnippet:
    project: Project
    identifier: str
    content: str
    version: int
    created_at: datetime
    updated_at: datetime

    def __str__(self):
        return f"{self.identifier} v{self.version}"
