from ninja import Router
from django.shortcuts import render
from uuid import UUID
from core.datastore.repos.spec_version_repo import SpecVersionRepo
import json

router = Router(tags=["Spec"])
spec_repo = SpecVersionRepo()


@router.get("projects/{project_id}/spec/")
async def get_spec(request, project_id: UUID):
    latest = await spec_repo.col.find_one(
        {"project_id": str(project_id)},
        sort=[("version", -1)]
    )
    content = latest["content"] if latest else "<p>No spec yet.</p>"
    return render(request, "partials/spec_editor.html", {
        "project_id": str(project_id),
        "content": content,
    })

@router.patch("projects/{project_id}/spec/")
async def patch_spec(request, project_id: UUID):
    raw = await request.body()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError:
        payload = {"content": raw.decode("utf-8") if raw else ""}

    content = payload.get("content", "")
    author = request.session.get("agent_name", "PM")
    await spec_repo.add_version(str(project_id), content, author=author)
    return {"status": "ok"}
