from typing import Optional, Any, Dict
from uuid import UUID
from datetime import datetime
from pymongo import DESCENDING
from core.infra.mongo import get_mongo_db
import json

class _SpecColProxy:
    def __init__(self, col):
        self._col = col

    async def find_one(self, *args, **kwargs):
        doc = await self._col.find_one(*args, **kwargs)
        if not doc:
            return doc
        data = doc.get("content")
        if isinstance(data, dict):
            sections = data.get("sections")
            if isinstance(sections, list) and sections:
                body = sections[0].get("body")
                if isinstance(body, str):
                    doc = dict(doc)
                    doc["content"] = body
        return doc

    def __getattr__(self, name):
        return getattr(self._col, name)

class SpecVersionRepo:
    def __init__(self):
        base_col = get_mongo_db()["spec_versions"]
        self._col = base_col
        self.col = _SpecColProxy(base_col)

    async def insert(self, doc: dict) -> str:
        doc["created_at"] = doc.get("created_at", datetime.utcnow())
        result = await self._col.insert_one(doc)
        return str(result.inserted_id)

    async def update(self, filter: dict, update: dict, upsert: bool = False):
        return await self._col.update_one(filter, {"$set": update}, upsert=upsert)

    async def find(self, filter: dict, sort=None, limit=0):
        cursor = self._col.find(filter)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        return await cursor.to_list(length=limit or 100)

    def _normalize_content(self, content: Any) -> Dict[str, Any]:
        if isinstance(content, dict):
            if isinstance(content.get("sections"), list):
                return content
            if isinstance(content.get("content"), str):
                return {
                    "sections": [{"name": "raw", "body": content["content"]}],
                    "meta": {"migratedFrom": "json-content"},
                }
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
                return self._normalize_content(parsed)
            except Exception:
                return {
                    "sections": [{"name": "raw", "body": content}],
                    "meta": {"migratedFrom": "plaintext"},
                }
        return {
            "sections": [{"name": "raw", "body": str(content)}],
            "meta": {"migratedFrom": "unknown"},
        }

    async def add_version(self, project_id: str, content: Any, author: str, diff: Optional[str] = None):
        latest = await self._col.find_one({"project_id": project_id}, sort=[("version", DESCENDING)])
        next_version = (latest["version"] + 1) if latest else 1
        return await self.insert({
            "project_id": project_id,
            "version": next_version,
            "content": self._normalize_content(content),
            "author": author,
            "diff": diff
        })
