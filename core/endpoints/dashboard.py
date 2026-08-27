from ninja import Path, Router, Schema
from ninja.errors import HttpError

from core.datastore.repos.project_repo import ProjectRepo
from core.datastore.repos.ticket_repo import TicketRepo

router = Router(tags=["Dashboard"])
ticket_repo = TicketRepo()
project_repo = ProjectRepo()


class DashboardOut(Schema):
    open_tasks: int
    done_tasks: int


@router.get("{project_id}/dashboard/", response=DashboardOut)
async def project_dashboard(
    request,
    project_id: str = Path(..., description="Project ID"),
):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HttpError(404, "Project not found")

    tickets = await ticket_repo.list_all(project.id)
    open_count = len([ticket for ticket in tickets if ticket.column != "Done"])
    done_count = len([ticket for ticket in tickets if ticket.column == "Done"])

    return DashboardOut(open_tasks=open_count, done_tasks=done_count)
