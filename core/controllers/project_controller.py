# core/controllers/project_controller.py (fully consolidated)
from datetime import timedelta, datetime

from core.dataclasses.project import Project
from core.services.project_service import ProjectsService
from core.services.session_service import SessionService


class ProjectsController:
    def __init__(self):
        self.service = ProjectsService()

    async def list_projects(self):
        projects = await self.service.list_projects()
        enriched = []
        for p in projects:
            stats = await self.service.get_ticket_stats(str(p.id))
            p.open_tickets = stats["open"]
            p.done_tickets = stats["done"]
            enriched.append(p)
        return enriched

    async def create_project(self, name: str) -> Project:
        return await self.service.create_project(name)

    async def update_project(self, project_id: str, patch: dict) -> Project:
        return await self.service.update_project(project_id, patch)

    async def get_project(self, project_id: str) -> Project:
        return await self.service.get_project_by_id(project_id)

    async def deactivate_project(self, project_id: str):
        return await self.update_project(project_id, {"active": False})

    async def get_dashboard_metrics(self, project_id: str) -> dict:
        stats = await self.service.get_ticket_stats(project_id)
        tickets = self.service.ticket_repo.get_all_tickets(project_id)
        milestone_ticket = next((t for t in tickets if "milestone" in t.get("label", "").lower()), None)
        return {
            "next_milestone": milestone_ticket["title"] if milestone_ticket else "Next Feature Drop",
            "open_tasks": stats["open"],
            "done_tasks": stats["done"],
            "active_branches": 3,
            "test_pass_rate": 88,
            "activity_logs": self.get_activity_logs(project_id)
        }

    def get_activity_logs(self, project_id: str) -> list[dict]:
        return [
            {
                "timestamp": datetime.utcnow() - timedelta(minutes=5),
                "agent": "DevBot",
                "action": "Assigned Ticket",
                "details": "T123 → @Dev"
            },
            {
                "timestamp": datetime.utcnow() - timedelta(minutes=15),
                "agent": "TestRunner",
                "action": "Test Passed",
                "details": "build_2025_05_11_green"
            }
        ]

    async def get_current_project(self, request):
        project_id = await ProjectsService().get_project_id_from_request(request)
        if not project_id:
            return None
        return await self.service.get_project_by_id(project_id)

    async def set_current_project(self, request, project_id: str) -> bool:
        if await self.service.get_project_by_id(project_id):
            request.session["current_project_id"] = project_id
            return True
        return False

    async def get_all_with_context(self, request):
        session = await SessionService().manage(request)
        return {
            "projects": await self.service.list_active_projects(),
            "current_project_id": session.project_id
        }

    async def get_milestones(self, project_id: str) -> list[dict]:
        return await self.service.get_milestones(project_id)

    async def get_latest_spec(self, project_id: str) -> dict | None:
        return await self.service.get_latest_spec(project_id)

    async def get_latest_ticket(self, project_id: str) -> dict | None:
        return await self.service.get_latest_ticket(project_id)

    def get_code_file(self, project_id: str, filename: str) -> str:
        return self.service.get_code_file(project_id, filename)

    def save_code_file(self, project_id: str, filename: str, code: str):
        return self.service.save_code_file(project_id, filename, code)

