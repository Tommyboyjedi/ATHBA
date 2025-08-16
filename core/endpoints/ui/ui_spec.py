from django.shortcuts import render
from ninja import Router
import json

from core.controllers.project_controller import ProjectsController
from core.services.spec_service import SpecService

router = Router(tags=["spec"])
pc = ProjectsController()

@router.get("/")
async def load_spec(request):
    project_id = request.session.get("project_id")
    if not project_id:
        return render(request, "partials/spec_editor.html", {
            "content": "<p>Please select or create a project to begin editing the specification.</p>"
        })

    content = await SpecService().get_latest_content(str(project_id))
    if not content:
        content = "<p>No spec yet. Click Save to initialize, or tell the Spec agent to 'start spec'.</p>"
    return render(request, "partials/spec_editor.html", {
        "content": content
    })

@router.patch("/")
async def save_spec(request):
    project_id = request.session.get("project_id")
    if not project_id:
        return {"status": "error", "message": "No active project in session."}

    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        payload = {"content": raw.decode("utf-8") if raw else ""}

    content = payload.get("content", "")
    author = request.session.get("agent_name", "PM")
    # If no existing spec, initialize, else overwrite by appending a new version with content provided
    service = SpecService()
    exists = await service.spec_exists(str(project_id))
    if not exists and content:
        # initialize with provided content
        await service.append_content(str(project_id), content, author=author)
    else:
        await service.append_content(str(project_id), content, author=author)
    return {"status": "ok"}
