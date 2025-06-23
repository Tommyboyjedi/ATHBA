from django.shortcuts import render
from ninja import Router

from core.dataclasses.project import Project
from core.services.project_service import ProjectsService

router = Router(tags=["Projects"])
ps = ProjectsService()

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

@router.post("/{project_id}/deactivate/")
async def deactivate_project(request, project_id: str):
    project = await ps.get_project_by_id(project_id)
    project.active = False
    await ps.update_project(project)
    projects = await ps.list_active_projects()
    return render(request, "partials/overview.html", {"projects": projects})


