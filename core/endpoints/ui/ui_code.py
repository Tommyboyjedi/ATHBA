
from django.shortcuts import render, redirect
from ninja import Form, Router

from core.controllers.project_controller import ProjectsController
from core.services.project_service import ProjectsService

router = Router(tags=["code"])
pc = ProjectsController()
@router.get("/")
def code_panel_entry(request):
    return render(request, "partials/code_panel.html")


@router.get("/edit")
async def edit_code(request):
    project_id = await ProjectsService().get_project_id_from_request(request)
    if not project_id:
        return redirect("/")  # or handle fallback
    filename = ''
    code_text = pc.get_code_file(project_id, filename)
    return render(request, "partials/code_edit.html", {
        "code_text": code_text
    })


@router.post("/save")
async def save_code(request, code_text: str = Form(...)):
    project_id = await ProjectsService().get_project_id_from_request(request)
    if not project_id:
        return redirect("/")  # or handle fallback
    filename = ''
    pc.save_code_file(project_id, filename, code_text)
    return render(request, "partials/code.html", {
        "code_text": code_text
    })


@router.get("/list/")
async def code_file_list(request):
    project_id = await ProjectsService().get_project_id_from_request(request)
    if not project_id:
        return redirect("/")  # or handle fallback
    files = await pc.list_code_files(project_id)
    return render(request, "partials/code_list.html", {"files": files})


@router.get("/view/{filename}")
async def view_code_file(request, filename: str):
    project_id = await ProjectsService().get_project_id_from_request(request)
    if not project_id:
        return redirect("/")  # or handle fallback
    code = pc.get_code_file(project_id, filename)
    return render(request, "partials/code_edit.html", {
        "filename": filename,
        "code": code
    })


@router.post("/save/{filename}")
async def save_code_file(request, filename: str, code: str = Form(...)):
    project_id = await ProjectsService().get_project_id_from_request(request)
    if not project_id:
        return redirect("/")  # or handle fallback
    pc.save_code_file(project_id, filename, code)
    return render(request, "partials/code_edit.html", {
        "filename": filename,
        "code": code
    })
