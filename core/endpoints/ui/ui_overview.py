from django.shortcuts import render
from ninja import Router

from core.services.project_service import ProjectsService

router = Router(tags=["overview"])
ps = ProjectsService()

@router.get("/")
async def load_overview(request):
    projects = await ps.list_active_projects()
    return render(request, "partials/overview.html", {"projects": projects})

