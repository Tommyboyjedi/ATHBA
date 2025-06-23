from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class HistoryEntry:
    timestamp: datetime
    field: str
    old: Any
    new: Any
    actor: str
