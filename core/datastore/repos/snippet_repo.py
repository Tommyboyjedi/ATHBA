from datetime import UTC, datetime

from bson import ObjectId

from core.datastore.repos.mongo_requests import (
    MongoFindRequest,
    MongoUpdateRequest,
    SnippetSaveRequest,
)
from core.infra.mongo import get_mongo_db


class SnippetRepo:
    def __init__(self):
        self.col = get_mongo_db()["snippets"]

    async def insert(self, doc: dict) -> str:
        doc["created_at"] = doc.get("created_at", datetime.now(UTC))
        result = await self.col.insert_one(doc)
        return str(result.inserted_id)

    async def update(self, request: MongoUpdateRequest):
        return await self.col.update_one(
            request.filter,
            {"$set": request.update},
            upsert=request.upsert,
        )

    async def find(self, request: MongoFindRequest):
        cursor = self.col.find(request.filter)
        if request.sort:
            cursor = cursor.sort(request.sort)
        if request.limit:
            cursor = cursor.limit(request.limit)
        return await cursor.to_list(length=request.limit or 100)

    async def save_snippet(self, request: SnippetSaveRequest):
        return await self.insert(
            {
                "project_id": request.project_id,
                "snippet_id": request.snippet_id,
                "language": request.language,
                "code": request.code,
                "origin": request.origin,
                "context": request.context,
            }
        )

    async def list_by_project(self, project_id: str) -> list[dict]:
        return await self.col.find({"project_id": project_id}).to_list(length=1000)

    async def get_by_id(self, snippet_id: str) -> dict | None:
        return await self.col.find_one({"_id": ObjectId(snippet_id)})
