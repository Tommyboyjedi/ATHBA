from datetime import datetime
from core.infra.mongo import get_mongo_db

class AgentLogRepo:
    def __init__(self):
        self.col = get_mongo_db()["agent_logs"]

    async def insert(self, doc: dict) -> str:
        doc["created_at"] = doc.get("created_at", datetime.utcnow())
        result = await self.col.insert_one(doc)
        return str(result.inserted_id)

    async def update(self, filter: dict, update: dict, upsert=False):
        return await self.col.update_one(filter, {"$set": update}, upsert=upsert)

    async def find(self, filter: dict, sort=None, limit=0):
        cursor = self.col.find(filter)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit or 100)

    async def list_by_project(self, project_id: str, limit: int = 100) -> list[dict]:
        return await self.col.find(
            {"project_id": project_id}
        ).sort("timestamp", -1).limit(limit).to_list(length=limit)

    async def log(self, project_id: str, agent: str, action: str, details: dict):
        await self.insert({
            "project_id": project_id,
            "agent": agent,
            "action": action,
            "details": details,
            "timestamp": datetime.utcnow(),
        })
