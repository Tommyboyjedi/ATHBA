from dataclasses import dataclass, field, asdict
from datetime import datetime

@dataclass
class ChatMessage:
    sender: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    session_id: str = None
    project_id: str = None
    metadata: dict = None

    def to_dict(self):
        return asdict(self)

    def with_session(self, session) -> "ChatMessage":
        self.session_id = session.session_id
        self.project_id = session.project_id
        return self
