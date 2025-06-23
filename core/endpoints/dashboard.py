from ninja import Router, Path
from django.shortcuts import get_object_or_404
from core.dataclasses.project import Project
from ninja import Schema
from core.datastore.repos.ticket_repo import TicketRepo

router = Router(tags=["Dashboard"])
ticket_repo = TicketRepo()


class DashboardOut(Schema):
    open_tasks: int
    done_tasks: int



@router.get("{project_id}/dashboard/", response=DashboardOut)
def project_dashboard(
    request,
    project_id: int = Path(..., description="Project ID"),
):
    p = get_object_or_404(Project, pk=project_id)
    tickets = ticket_repo.get_backlog_tickets(str(p.id))

    open_count = len([t for t in tickets if t.get("column") != "Done"])
    done_count = len([t for t in tickets if t.get("column") == "Done"])

    return DashboardOut(open_tasks=open_count, done_tasks=done_count)
