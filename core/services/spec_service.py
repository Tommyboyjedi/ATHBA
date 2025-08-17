from core.datastore.repos.spec_version_repo import SpecVersionRepo
from uuid import UUID
from html import escape


class SpecService:
    def __init__(self):
        self.repo = SpecVersionRepo()

    async def spec_exists(self, project_id: str) -> bool:
        existing = await self.repo.col.find_one({"project_id": project_id})
        return existing is not None

    async def initialize_spec(self, project_id: str, author: str = "Spec"):
        content = "<h1>Specification</h1><p>Let's define what this system should do...</p>"
        return await self.repo.add_version(project_id, content, author)

    async def get_latest_content(self, project_id: str) -> str:
        latest = await self.repo.col.find_one({"project_id": project_id}, sort=[("version", -1)])
        return latest.get("content", "") if latest else ""

    async def get_latest_version(self, project_id: str) -> int | None:
        latest = await self.repo.col.find_one({"project_id": project_id}, sort=[("version", -1)])
        return int(latest.get("version")) if latest and latest.get("version") is not None else None

    async def append_content(self, project_id: str, content_append_html: str, author: str = "Spec"):
        base = await self.get_latest_content(project_id)
        new_html = (base or "") + ("\n" if base else "") + content_append_html
        return await self.repo.add_version(project_id, new_html, author)

    async def finalize_spec(self, project_id: str, author: str = "Spec"):
        base = await self.get_latest_content(project_id)
        note = "<p><em>Specification finalized.</em></p>"
        new_html = (base or "") + ("\n" if base else "") + note
        return await self.repo.add_version(project_id, new_html, author)
