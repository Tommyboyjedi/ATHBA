from django.shortcuts import render
from ninja import Form, Router

from core.controllers.project_controller import ProjectsController
from core.datastore.repos.ticket_repo import TicketRepo
from core.services.project_service import ProjectsService

router = Router(tags=["kanban"])
pc = ProjectsController()
tr = TicketRepo()
column_list = ["Backlog", "To Do", "In Progress", "Review", "Done"]


@router.get("/")
def load_kanban(request):
    return render(request, "partials/kanban.html", {"column_list": column_list})


@router.get("/edit")
async def load_editable_kanban(request):
    project_id = await ProjectsService().get_project_id_from_request(request)
    tickets = tr.list_all(project_id) if project_id else []

    return render(request, "partials/kanban_edit.html", {
        "tickets": tickets,
        "columns": column_list
    })

@router.post("update/{ticket_id}")
async def update_ticket(request, ticket_id: str, title: str = Form(...), label: str = Form(...), eta: str = Form(...), column: str = Form(...)):
    await tr.update(ticket_id, {
        "title": title,
        "label": label,
        "eta": eta,
        "column": column
    })
    # Return updated kanban board
    project_id = await ProjectsService().get_project_id_from_request(request)
    tickets = tr.list_all(project_id) if project_id else []
    return render(request, "partials/kanban.html", {
        "tickets": tickets
    })
