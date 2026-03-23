"""Chat message dataclass for representing conversation messages."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
import base64
import json


@dataclass
class ChatMessage:
    """
    Represents a chat message in a conversation.
    
    Messages can be from users, agents, or the system. Each message includes
    a timestamp and can have optional metadata for additional context.
    
    Attributes:
        sender: Name of message sender (user, agent name, or "system")
        content: Message text content
        timestamp: ISO format timestamp (auto-generated if not provided)
        session_id: Session identifier for grouping messages
        project_id: Project identifier for conversation context
        metadata: Additional message metadata (e.g., error flags, actions)
    """
    sender: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    session_id: str = None
    project_id: str = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """
        Convert message to dictionary for serialization.
        
        Returns:
            Dictionary representation of the message
        """
        return asdict(self)
    
    def get_formatted_timestamp(self) -> str:
        """
        Return human-readable relative timestamp.
        
        Converts the ISO timestamp to a user-friendly format:
        - "just now" for < 1 minute
        - "X minutes ago" for < 1 hour
        - "X hours ago" for < 1 day
        - Full date/time for older messages
        
        Returns:
            Human-readable timestamp string
        """
        try:
            dt = datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
            now = datetime.utcnow()
            diff = now - dt
            
            if diff.total_seconds() < 60:
                return "just now"
            elif diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
            elif diff.total_seconds() < 86400:
                hours = int(diff.total_seconds() / 3600)
                return f"{hours} hour{'s' if hours > 1 else ''} ago"
            else:
                return dt.strftime("%b %d, %Y at %I:%M %p")
        except Exception:
            return self.timestamp

    def with_session(self, session) -> "ChatMessage":
        """
        Associate message with a session object.
        
        Args:
            session: Session object containing session_id and project_id
            
        Returns:
            Self for method chaining
        """
        self.session_id = session.session_id
        self.project_id = session.project_id
        return self

    def with_session_key(self, session_key: str) -> "ChatMessage":
        """
        Associate message with a Django session key.
        
        Attempts to extract project_id from the session key by decoding
        the Django session data. Falls back gracefully if parsing fails.
        
        Args:
            session_key: Django session key string
            
        Returns:
            Self for method chaining
        """
        self.session_id = session_key
        try:
            # Django session key format: <session_data>:<salt>:<signature>
            # session_data is base64 encoded JSON
            session_data_b64 = session_key.split(':')[0]
            # Pad the base64 string if needed
            session_data_json = base64.urlsafe_b64decode(
                session_data_b64 + '=' * (-len(session_data_b64) % 4)
            ).decode('utf-8')
            session_data = json.loads(session_data_json)
            self.project_id = session_data.get('project_id')
        except Exception:
            # If parsing fails, we can't get project_id - continue without it
            self.project_id = None
        return self
