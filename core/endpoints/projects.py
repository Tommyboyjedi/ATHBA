from django.shortcuts import render
from ninja import Router, Schema

from core.dataclasses.project import Project
from core.services.project_service import ProjectsService

router = Router(tags=["Projects"])
ps = ProjectsService()


class ActiveProjectResponse(Schema):
    id: str | None
    name: str | None

@router.get("/", response=list[Project])
async def list_projects(request):
    return await ps.list_projects()

@router.post("/", response=Project)
def create_project(request, data: Project):
    return ps.create_project(data.name)

@router.patch("/{project_id}", response=Project)
def update_project(request, project_id: str, data: Project):
    return ps.update_project(project_id, data)

@router.get("/{project_id}", response=Project)
def get_project(request, project_id: str):
    return ps.get_project_by_id(project_id)


@router.get("/active/", response=ActiveProjectResponse)
async def get_active_project(request):
    project_id = request.session.get("project_id")
    name = None
    if project_id:
        try:
            project = await ps.get_project_by_id(project_id)
            if project:
                name = project.name
        except Exception:
            name = None
    return {"id": project_id, "name": name}

@router.post("/{project_id}/deactivate/")
async def deactivate_project(request, project_id: str):
    project = await ps.get_project_by_id(project_id)
    project.active = False
    await ps.update_project(project)
    projects = await ps.list_active_projects()
    return render(request, "partials/overview.html", {"projects": projects})


