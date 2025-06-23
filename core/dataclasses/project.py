from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.dataclasses.priority import Priority


@dataclass
class Project:

    _id: Optional[str] = None
    name: str = ""
    spec_html: Optional[str] = None
    active: bool = True
    locked: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    open_tickets: int = 0
    done_tickets: int = 0
    priority: Priority = Priority.low
    paused: bool = False

    @property
    def id(self):
        return self._id if self._id else ''

    def to_dict(self):
        return {
            "_id": self._id,
            "name": self.name,
            "spec_html": self.spec_html,
            "active": self.active,
            "locked": self.locked,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "open_tickets": self.open_tickets,
            "done_tickets": self.done_tickets,
            "priority": self.priority.value,
            "paused": self.paused
        }
