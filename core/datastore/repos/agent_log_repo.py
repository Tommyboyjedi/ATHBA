from datetime import datetime

from core.datastore.repos.mongo_requests import (
    AgentLogEntry,
    MongoFindRequest,
    MongoUpdateRequest,
)
from core.infra.mongo import get_mongo_db


class AgentLogRepo:
    def __init__(self):
        self.col = get_mongo_db()["agent_logs"]

    async def insert(self, doc: dict) -> str:
        doc["created_at"] = doc.get("created_at", datetime.utcnow())
        result = await self.col.insert_one(doc)
        return str(result.inserted_id)

    async def update(self, request_or_filter, *args):
        request = request_or_filter
        if not isinstance(request, MongoUpdateRequest):
            update = args[0]
            upsert = args[1] if len(args) > 1 else False
            request = MongoUpdateRequest(filter=request_or_filter, update=update, upsert=upsert)
        return await self.col.update_one(request.filter, {"$set": request.update}, upsert=request.upsert)

    async def find(self, request_or_filter, *args):
        request = request_or_filter
        if not isinstance(request, MongoFindRequest):
            sort = args[0] if len(args) > 0 else []
            limit = args[1] if len(args) > 1 else 0
            request = MongoFindRequest(filter=request_or_filter, sort=sort or [], limit=limit)
        cursor = self.col.find(request.filter)
        if request.sort:
            cursor = cursor.sort(request.sort)
        if request.limit:
            cursor = cursor.limit(request.limit)
        return await cursor.to_list(length=request.limit or 100)

    async def list_by_project(self, project_id: str, limit: int = 100) -> list[dict]:
        return await self.col.find({"project_id": project_id}).sort("timestamp", -1).limit(limit).to_list(length=limit)

    async def log(self, entry: AgentLogEntry):
        await self.insert(
            {
                "project_id": entry.project_id,
                "agent": entry.agent,
                "action": entry.action,
                "details": entry.details,
                "timestamp": datetime.utcnow(),
            }
        )
