from core.datastore.repos.spec_version_repo import SpecVersionRepo
from uuid import UUID


class SpecService:
    def __init__(self):
        self.repo = SpecVersionRepo()

    async def spec_exists(self, project_id: str) -> bool:
        existing = await self.repo.col.find_one({"project_id": project_id})
        return existing is not None

    async def initialize_spec(self, project_id: str, author: str = "Spec"):
        content = "<h1>Specification</h1><p>Let's define what this system should do...</p>"
        return await self.repo.add_version(project_id, content, author)
