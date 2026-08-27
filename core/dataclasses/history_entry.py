from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class HistoryEntry:
    """Canonical ticket/project history record with legacy constructor compatibility.

    New code should prefer ``event``, ``actor`` and ``details``. ``field/old/new``
    and ``agent/action`` are retained temporarily so existing persisted records and
    pre-Rack-AI agent behaviours can be migrated without a flag day.
    """

    timestamp: datetime
    actor: str = ""
    event: str = ""
    details: str = ""
    field: str = ""
    old: Any = None
    new: Any = None
    agent: str = ""
    action: str = ""

    def __post_init__(self) -> None:
        if not self.actor and self.agent:
            self.actor = self.agent
        if not self.event and self.action:
            self.event = self.action
