# core/repos/project_repo.py

from core.dataclasses.project import Project
from core.infra.mongo import get_mongo_db
from bson import ObjectId
from datetime import datetime

class ProjectRepo:
    def __init__(self):
        db = get_mongo_db()
        self.collection = db.projects
        self.milestones_col = db.milestones

    async def get_by_id(self, project_id: str) -> Project:
        doc = await self.collection.find_one({"_id": ObjectId(project_id)})
        return Project(**doc) if doc else None

    async def list_all(self) -> list[Project]:
        cursor = self.collection.find({})
        return [Project(**doc) async for doc in cursor]

    async def create(self, name: str) -> Project:
        now = datetime.utcnow()
        new_doc = {
            "name": name,
            "active": True,
            "locked": False,
            "created_at": now,
            "updated_at": now,
            "spec_html": "",
        }
        result = await self.collection.insert_one(new_doc)
        new_doc["_id"] = result.inserted_id
        return Project(**new_doc)

    async def update(self, project: Project) -> Project:
        project.updated_at = datetime.utcnow()
        await self.collection.update_one({"_id": ObjectId(project.id)}, {"$set": project.to_dict()})
        return await self.get_by_id(project.id)

    async def lock(self, project_id: str):
        project = await self.get_by_id(project_id)
        if not project:
            return None
        project.locked = True
        return await self.update(project)

    async def get_milestones(self, project_id: str) -> list[dict]:
        return await self.milestones_col.find({"project_id": project_id}).to_list(length=100)
