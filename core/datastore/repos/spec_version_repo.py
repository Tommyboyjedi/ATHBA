from typing import Optional, Any, Dict
from uuid import UUID
from datetime import datetime
from pymongo import DESCENDING
from core.infra.mongo import get_mongo_db
import json

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

    def _normalize_content(self, content: Any) -> Dict[str, Any]:
        if isinstance(content, dict):
            if "sections" in content and isinstance(content["sections"], list):
                return content
            if "content" in content and isinstance(content["content"], str):
                return {
                    "sections": [{"name": "raw", "body": content["content"]}],
                    "meta": {"migratedFrom": "json-content"}
                }
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                return self._normalize_content(parsed)
            except Exception:
                return {
                    "sections": [{"name": "raw", "body": content}],
                    "meta": {"migratedFrom": "plaintext"}
                }
        return {
            "sections": [{"name": "raw", "body": str(content)}],
            "meta": {"migratedFrom": "unknown"}
        }

    async def add_version(self, project_id: str, content: Any, author: str, diff: Optional[str] = None):
        latest = await self.col.find_one({"project_id": project_id}, sort=[("version", DESCENDING)])
        next_version = (latest["version"] + 1) if latest else 1
        return await self.insert({
            "project_id": project_id,
            "version": next_version,
            "content": self._normalize_content(content),
            "author": author,
            "diff": diff
        })
