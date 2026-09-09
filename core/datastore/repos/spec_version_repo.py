import json
from datetime import UTC, datetime
from typing import Any, Dict

from pymongo import DESCENDING

from core.datastore.repos.mongo_requests import (
    MongoFindRequest,
    MongoUpdateRequest,
    SpecVersionCreateRequest,
)
from core.infra.mongo import get_mongo_db


class _SpecColProxy:
    def __init__(self, source):
        self._source = source

    @property
    def _col(self):
        if hasattr(self._source, "_collection"):
            return self._source._collection
        return self._source

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
    def __init__(self, collection=None):
        self._base_col = collection
        self.col = _SpecColProxy(self)

    @property
    def _collection(self):
        if self._base_col is None:
            self._base_col = get_mongo_db()["spec_versions"]
        return self._base_col

    async def insert(self, doc: dict) -> str:
        doc["created_at"] = doc.get("created_at", datetime.now(UTC))
        result = await self._collection.insert_one(doc)
        return str(result.inserted_id)

    async def update(self, request_or_filter, *args):
        request = request_or_filter
        if not isinstance(request, MongoUpdateRequest):
            update = args[0]
            upsert = args[1] if len(args) > 1 else False
            request = MongoUpdateRequest(filter=request_or_filter, update=update, upsert=upsert)
        return await self._collection.update_one(
            request.filter,
            {"$set": request.update},
            upsert=request.upsert,
        )

    async def find(self, request_or_filter, *args):
        request = request_or_filter
        if not isinstance(request, MongoFindRequest):
            sort = args[0] if len(args) > 0 else []
            limit = args[1] if len(args) > 1 else 0
            request = MongoFindRequest(filter=request_or_filter, sort=sort or [], limit=limit)
        cursor = self._collection.find(request.filter)
        if request.sort:
            cursor = cursor.sort(request.sort)
        if request.limit:
            cursor = cursor.limit(request.limit)
        return await cursor.to_list(length=request.limit or 100)

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

    async def add_version(self, request: SpecVersionCreateRequest):
        latest = await self._collection.find_one(
            {"project_id": request.project_id},
            sort=[("version", DESCENDING)],
        )
        next_version = (latest["version"] + 1) if latest else 1
        return await self.insert(
            {
                "project_id": request.project_id,
                "version": next_version,
                "content": self._normalize_content(request.content),
                "author": request.author,
                "diff": request.diff,
            }
        )
