
from django.shortcuts import render, redirect

from core.controllers.project_controller import ProjectsController
from core.endpoints.projects import router


async def index(request):
    ctrl = ProjectsController()
    context = await ctrl.get_all_with_context(request)
    return render(request, "base.html", context)


@router.post("/switch/")
async def switch_project(request):
    project_id = request.POST.get("project_id")
    request.session["current_project_id"] = project_id
    return redirect("/")

