# core/services/project_service.py
from core.dataclasses.project import Project
from core.datastore.repos.project_repo import ProjectRepo
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.session_service import SessionService


class ProjectsService:
    def __init__(self):
        self.project_repo = ProjectRepo()
        self.ticket_repo = TicketRepo()

    async def list_projects(self) -> list[Project]:
        return await self.project_repo.list_all()

    async def list_active_projects(self) -> list[Project]:
        projects = await self.project_repo.list_all()
        return [p for p in projects if p.active]

    async def get_project_by_id(self, project_id: str) -> Project:
        return await self.project_repo.get_by_id(project_id)

    async def count_tickets(self, project_id: str, column: str | None = None) -> int:
        return await self.ticket_repo.count(project_id, column)

    async def get_ticket_stats(self, project_id: str) -> dict:
        open_count = await self.count_tickets(project_id)
        done_count = await self.count_tickets(project_id, column="Done")
        return {
            "open": open_count - done_count,
            "done": done_count
        }

    async def lock_project(self, project_id: str):
        return await self.project_repo.lock(project_id)

    async def update_project(self, project: Project):
        return await self.project_repo.update(project)

    async def create_project(self, name: str):
        return await self.project_repo.create(name)

    def get_code_file(self, project_id: str, filename: str) -> str:
        return self.ticket_repo.get_file(project_id, filename)

    def save_code_file(self, project_id: str, filename: str, code: str):
        self.ticket_repo.save_file(project_id, filename, code)

    async def get_milestones(self, project_id: str) -> list[dict]:
        return self.ticket_repo.get_milestones(project_id)

    async def get_latest_spec(self, project_id: str) -> dict | None:
        return self.ticket_repo.get_latest_spec(project_id)

    async def get_latest_ticket(self, project_id: str) -> dict | None:
        return self.ticket_repo.get_latest_ticket(project_id)

    async def get_project_from_request(self, request):
        session = await SessionService().manage(request)
        try:
            return await self.get_project_by_id(session.project_id)
        except Exception:
            return None

    async def get_project_id_from_request(self, request):
        session = await SessionService().manage(request)
        return session.project_id

    async def rename_project(self, project_id: str, new_name: str) -> Project | None:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            return None
        project.name = new_name
        return await self.project_repo.update(project)

