from dataclasses import dataclass

from ninja import Schema

@dataclass
class HistoryQuery:
    project_id: str
    session_id: str
    limit: int = 50
