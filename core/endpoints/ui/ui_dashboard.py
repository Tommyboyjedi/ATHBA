from django.shortcuts import render, redirect
from ninja import Router
from core.controllers.project_controller import ProjectsController
from core.services.project_service import ProjectsService

router = Router(tags=["dashboard"])
pc = ProjectsController()
@router.get("/")
async def load_dashboard(request):
    project_id = await ProjectsService().get_project_id_from_request(request)
    if not project_id:
        return render(request, "partials/dashboard.html", {
            "next_milestone": "No project selected",
            "open_tasks": 0,
            "active_branches": 0,
            "test_pass_rate": 0,
            "activity_logs": [],
        })

    stats = pc.get_dashboard_metrics(project_id)
    return render(request, "partials/dashboard.html", stats)


@router.get("/activity")
async def refresh_activity_logs(request):
    project_id = await ProjectsService().get_project_id_from_request(request)
    logs = pc.get_activity_logs(project_id) if project_id else []
    return render(request, "partials/dashboard_activity_table.html", {
        "activity_logs": logs
    })
