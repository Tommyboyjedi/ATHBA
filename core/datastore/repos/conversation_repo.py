"""Repository for managing conversation/chat message storage in MongoDB."""
from datetime import datetime
from typing import List
from bson import ObjectId

from core.infra.mongo import get_mongo_db


class ConversationRepo:
    """
    Repository for conversation and chat message persistence.
    
    Stores chat messages grouped by session and project in MongoDB.
    Each conversation document contains a list of messages with metadata.
    """
    
    def __init__(self):
        """Initialize repository with MongoDB collection."""
        self.col = get_mongo_db()["conversations"]

    async def append_message(self, message) -> None:
        """
        Append a message to a conversation.
        
        Creates a new conversation document if one doesn't exist for the
        session/project combination.
        
        Args:
            message: ChatMessage instance to append
            
        Raises:
            ValueError: If message is missing session_id or project_id
        """
        message_dict = message.to_dict()
        session_id = message_dict.get("session_id")
        project_id = message_dict.get("project_id")

        if not session_id or not project_id:
            raise ValueError("ChatMessage is missing session_id or project_id")

        await self.col.update_one(
            {"project_id": project_id, "session_id": session_id},
            {
                "$push": {"messages": message_dict},
                "$set": {"last_updated": datetime.utcnow()}
            },
            upsert=True
        )

    async def get_recent(self, session_id: str, limit: int = 50) -> List[dict]:
        """
        Get recent messages for a session.
        
        Retrieves the most recent messages up to the specified limit.
        Converts ObjectId and datetime fields to strings for JSON serialization.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return (default: 50)
            
        Returns:
            List of message dictionaries with serialized fields
        """
        doc = await self.col.find_one(
            {"session_id": session_id},
            projection={"_id": 1, "messages": {"$slice": -limit}}
        )
        msgs = doc.get("messages", []) if doc else []

        clean: List[dict] = []
        for m in msgs:
            m = dict(m)
            m.pop("_id", None)
            for k, v in m.items():
                if isinstance(v, ObjectId):
                    m[k] = str(v)
                elif isinstance(v, datetime):
                    m[k] = v.isoformat()
            clean.append(m)
        return clean

    async def list_by_project(self, project_id: str) -> list[dict]:
        """
        List all conversations for a project.
        
        Args:
            project_id: Project identifier
            
        Returns:
            List of conversation documents (up to 100)
        """
        return await self.col.find({"project_id": project_id}).to_list(length=100)
    
    async def clear_conversation(self, session_id: str) -> None:
        """
        Clear all messages for a given session.
        
        Removes all messages from the conversation while preserving
        the conversation document structure.
        
        Args:
            session_id: Session identifier for conversation to clear
        """
        await self.col.update_one(
            {"session_id": session_id},
            {
                "$set": {
                    "messages": [],
                    "last_updated": datetime.utcnow()
                }
            }
        )
