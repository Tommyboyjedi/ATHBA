from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.dataclasses.projses import Projses


@dataclass
class AgentMessage:
    sender: str
    text: str
    session: Projses
    timestamp: Optional[str] = None
    error: bool = False

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "text": self.text,
            "timestamp": self.timestamp or datetime.utcnow().isoformat(),
        }
