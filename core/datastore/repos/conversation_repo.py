from datetime import datetime
from typing import List
from bson import ObjectId

from core.infra.mongo import get_mongo_db

class ConversationRepo:
    def __init__(self):
        self.col = get_mongo_db()["conversations"]

    async def append_message(self, message) -> None:
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
        return await self.col.find({"project_id": project_id}).to_list(length=100)
