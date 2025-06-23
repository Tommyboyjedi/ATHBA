from django.shortcuts import render
from ninja import Router

from core.controllers.project_controller import ProjectsController

router = Router(tags=["nav"])
pc = ProjectsController()

@router.get("/")
async def nav_partial(request):
    context = await pc.get_all_with_context(request)
    return render(request, "partials/nav.html", context)
