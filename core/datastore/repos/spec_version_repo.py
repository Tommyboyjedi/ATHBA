from typing import Optional
from uuid import UUID
from datetime import datetime
from pymongo import DESCENDING
from core.infra.mongo import get_mongo_db

class SpecVersionRepo:
    def __init__(self):
        self.col = get_mongo_db()["spec_versions"]

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

    async def add_version(self, project_id: str, content: str, author: str, diff: Optional[str] = None):
        latest = await self.col.find_one({"project_id": project_id}, sort=[("version", DESCENDING)])
        next_version = (latest["version"] + 1) if latest else 1
        return await self.insert({
            "project_id": project_id,
            "version": next_version,
            "content": content,
            "author": author,
            "diff": diff
        })
