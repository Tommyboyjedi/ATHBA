from ninja import Router
from django.shortcuts import render
from uuid import UUID
from core.datastore.repos.spec_version_repo import SpecVersionRepo

router = Router(tags=["Spec"])
spec_repo = SpecVersionRepo()


@router.get("projects/{project_id}/spec/")
async def get_spec(request, project_id: UUID):
    latest = await spec_repo.col.find_one(
        {"project_id": project_id},
        sort=[("version", -1)]
    )
    content = latest["content"] if latest else "<p>No spec yet.</p>"
    return render(request, "partials/spec_editor.html", {
        "project_id": str(project_id),
        "content": content,
    })

@router.patch("projects/{project_id}/spec/")
async def patch_spec(request, project_id: UUID):
    data = await request.body()
    content = data.decode("utf-8")
    await spec_repo.add_version(project_id, content, author="PM")
    return { "status": "ok" }
