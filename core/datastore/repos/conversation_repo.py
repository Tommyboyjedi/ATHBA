"""Repository for managing conversation/chat message storage in MongoDB."""
from datetime import datetime
from typing import List

from bson import ObjectId

from core.infra.mongo import get_mongo_db


class ConversationRepo:
    def __init__(self, collection=None):
        self._col = collection

    @property
    def col(self):
        if self._col is None:
            self._col = get_mongo_db()["conversations"]
        return self._col

    async def append_message(self, message) -> None:
        message_dict = message.to_dict()
        session_id = message_dict.get("session_id")
        project_id = message_dict.get("project_id")

        if not session_id or not project_id:
            raise ValueError("ChatMessage is missing session_id or project_id")

        await self.col.update_one(
            {"project_id": project_id, "session_id": session_id},
            {"$push": {"messages": message_dict}, "$set": {"last_updated": datetime.utcnow()}},
            upsert=True,
        )

    async def get_recent(self, session_id: str, limit: int = 50) -> List[dict]:
        doc = await self.col.find_one(
            {"session_id": session_id},
            projection={"_id": 1, "messages": {"$slice": -limit}},
        )
        msgs = doc.get("messages", []) if doc else []

        clean: List[dict] = []
        for message in msgs:
            message = dict(message)
            message.pop("_id", None)
            for key, value in message.items():
                if isinstance(value, ObjectId):
                    message[key] = str(value)
                elif isinstance(value, datetime):
                    message[key] = value.isoformat()
            clean.append(message)
        return clean

    async def list_by_project(self, project_id: str) -> list[dict]:
        return await self.col.find({"project_id": project_id}).to_list(length=100)

    async def clear_conversation(self, session_id: str) -> None:
        await self.col.update_one(
            {"session_id": session_id},
            {"$set": {"messages": [], "last_updated": datetime.utcnow()}},
        )
