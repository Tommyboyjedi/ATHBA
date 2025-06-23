from dataclasses import dataclass
from datetime import datetime
from typing import List
from core.dataclasses.history_entry import HistoryEntry

@dataclass
class TicketModel:
    project_id: str
    title: str
    description: str
    due: datetime
    eta: str
    agents: List[str]
    label: str
    severity: str
    column: str
    created_at: datetime
    updated_at: datetime
    history: List[HistoryEntry]
    id: str
