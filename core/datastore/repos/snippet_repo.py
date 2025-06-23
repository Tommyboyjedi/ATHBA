from uuid import UUID
from datetime import datetime
from bson import ObjectId
from core.infra.mongo import get_mongo_db

class SnippetRepo:
    def __init__(self):
        self.col = get_mongo_db()["snippets"]

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

    async def save_snippet(self, project_id: UUID, snippet_id: UUID, language: str, code: str, origin: str, context: str):
        return await self.insert({
            "project_id": project_id,
            "snippet_id": snippet_id,
            "language": language,
            "code": code,
            "origin": origin,
            "context": context
        })

    async def list_by_project(self, project_id: str) -> list[dict]:
        return await self.col.find({"project_id": project_id}).to_list(length=100)

    async def get_by_id(self, snippet_id: str) -> dict | None:
        return await self.col.find_one({"_id": ObjectId(snippet_id)})
