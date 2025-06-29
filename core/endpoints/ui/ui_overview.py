from django.http import HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string
from ninja import Router

from core.services.project_service import ProjectsService

router = Router(tags=["overview"])
ps = ProjectsService()


@router.get("/")
async def load_overview(request):
    projects = await ps.list_active_projects()
    project_id = request.session.get("project_id")

    context = {"projects": projects, "project_id": project_id}

    # Render main content and OOB content
    overview_html = render_to_string("partials/overview.html", context, request=request)
    selector_html = render_to_string(
        "partials/_project_selector.html", context, request=request
    )

    return HttpResponse(overview_html + selector_html)
