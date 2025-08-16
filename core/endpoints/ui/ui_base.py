# core/endpoints/ui/ui_base.py
from django.shortcuts import render
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from core.controllers.project_controller import ProjectsController
from core.endpoints.projects import router


async def index(request):
    ctrl = ProjectsController()
    context = await ctrl.get_all_with_context(request)
    return render(request, "base.html", context)


@router.post("/switch/")
@csrf_exempt  # keep for now; later remove & send CSRF headers from HTMX
async def switch_project(request):
    project_id = request.POST.get("project_id")
    if not project_id:
        return HttpResponse(status=400)
    request.session["project_id"] = project_id
    # Important: do NOT redirect; HTMX caller expects no content
    return HttpResponse(status=204)
