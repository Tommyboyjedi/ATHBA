from dataclasses import dataclass, field, asdict
from datetime import datetime
import base64
import json

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

    def with_session_key(self, session_key: str) -> "ChatMessage":
        self.session_id = session_key
        try:
            # Django session key is <session_data>:<salt>:<signature>
            # session_data is base64 encoded JSON
            session_data_b64 = session_key.split(':')[0]
            # Pad the base64 string if needed
            session_data_json = base64.urlsafe_b64decode(
                session_data_b64 + '=' * (-len(session_data_b64) % 4)
            ).decode('utf-8')
            session_data = json.loads(session_data_json)
            self.project_id = session_data.get('project_id')
        except Exception:
            # If parsing fails, we can't get project_id.
            self.project_id = None
        return self
