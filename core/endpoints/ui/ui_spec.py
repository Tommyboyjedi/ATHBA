from django.shortcuts import render
from ninja import Router

from core.controllers.project_controller import ProjectsController

router = Router(tags=["spec"])
pc = ProjectsController()
@router.get("/")
def load_spec(request):
    return render(request, "partials/spec_editor.html", {
        "content": "<p>Edit your spec here...</p>"
    })
