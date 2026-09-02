from core.dataclasses.project import Project
from core.datastore.repos.mongo_requests import CodeFileSaveRequest
from core.services.project_service import ProjectsService


class ProjectsController:
    def __init__(self):
        self.service = ProjectsService()

    async def list_projects(self):
        return await self.service.list_projects()

    async def get_project(self, project_id: str):
        return await self.service.get_project_by_id(project_id)

    async def update_project(self, project: Project):
        return await self.service.update_project(project)

    async def create_project(self, name: str):
        return await self.service.create_project(name)

    async def lock_project(self, project_id: str):
        return await self.service.lock_project(project_id)

    async def get_milestones(self, project_id: str):
        return await self.service.get_milestones(project_id)

    async def get_latest_spec(self, project_id: str):
        return await self.service.get_latest_spec(project_id)

    async def get_latest_ticket(self, project_id: str):
        return await self.service.get_latest_ticket(project_id)

    async def rename_project(self, project_id: str, new_name: str):
        return await self.service.rename_project(project_id, new_name)

    def get_code_file(self, project_id: str, filename: str) -> str:
        return self.service.get_code_file(project_id, filename)

    async def list_code_files(self, project_id: str) -> list[str]:
        return await self.service.code_repo.list_files(project_id)

    def save_code_file(self, request_or_project_id, *args):
        if isinstance(request_or_project_id, CodeFileSaveRequest):
            return self.service.save_code_file(request_or_project_id)
        return self.service.save_code_file(request_or_project_id, *args)
