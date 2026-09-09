from datetime import datetime
from typing import List, Optional

from ninja import Path, Router, Schema
from ninja.errors import HttpError

from core.dataclasses.ticket_model import TicketModel
from core.datastore.repos.agent_log_repo import AgentLogRepo
from core.datastore.repos.mongo_requests import AgentLogEntry
from core.datastore.repos.project_repo import ProjectRepo
from core.datastore.repos.ticket_repo import TicketRepo

router = Router(tags=["Tickets"])
project_repo = ProjectRepo()


class TicketIn(Schema):
    title: str
    description: Optional[str] = None
    due: Optional[datetime] = None
    eta: Optional[str] = None
    agents: Optional[str] = None
    label: str
    severity: str
    column: Optional[str] = None


class TicketPatch(Schema):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    due: Optional[datetime] = None
    eta: Optional[str] = None
    agents: Optional[str] = None
    label: str
    severity: str
    column: Optional[str] = None


class TicketOut(Schema):
    id: str
    title: str
    description: Optional[str] = None
    due: Optional[datetime] = None
    eta: Optional[str] = None
    agents: Optional[str] = None
    label: str
    severity: str
    column: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


async def ensure_not_locked(project_id: str):
    project = await project_repo.get_by_id(project_id)
    if not project:
        raise HttpError(404, "Project not found")
    if project.locked:
        raise HttpError(409, "Project is in edit mode")
    return project


@router.get("/", response=List[TicketOut])
async def list_tickets(
    request,
    project_id: str = Path(..., description="Project ID from URL"),
):
    return await TicketRepo().list_all(project_id)


@router.post("/", response=TicketOut)
async def create_ticket(request, project_id: str, data: TicketIn):
    await ensure_not_locked(project_id)
    agent_list = data.agents.split(",") if data.agents else []
    model = TicketModel(
        project_id=project_id,
        title=data.title,
        description=data.description or "",
        due=data.due,
        eta=data.eta or "",
        agents=agent_list,
        label=data.label,
        severity=data.severity,
        column=data.column or "Backlog",
    )
    return await TicketRepo().create(model)


@router.patch("/{ticket_id}", response=TicketOut)
async def update_ticket(request, project_id: str, ticket_id: str, data: TicketIn):
    await ensure_not_locked(project_id)
    updates = data.model_dump(exclude_unset=True)
    if "agents" in updates and updates["agents"] is not None:
        updates["agents"] = updates["agents"].split(",")
    updated = await TicketRepo().update(ticket_id, updates)
    if not updated:
        raise HttpError(404, "Ticket not found")
    return updated


@router.patch("/batch-update", response=List[TicketOut])
async def batch_update(request, project_id: str, tickets: List[TicketPatch]):
    project = await ensure_not_locked(project_id)
    project.locked = True
    await project_repo.update(project)
    try:
        repo = TicketRepo()
        existing_ids = set(await repo.list_ids_by_project(project_id))
        incoming_ids = {ticket.id for ticket in tickets if ticket.id}
        to_delete = existing_ids - incoming_ids
        if to_delete:
            await repo.delete_many(project_id, list(to_delete))
        results = []
        for ticket in tickets:
            data = ticket.model_dump(exclude_unset=True)
            ticket_id = data.pop("id", None)
            if "agents" in data and data["agents"] is not None:
                data["agents"] = data["agents"].split(",")
            if ticket_id:
                updated = await repo.update(ticket_id, data)
                if updated:
                    results.append(updated)
            else:
                results.append(await repo.create(TicketModel(project_id=project_id, **data)))
        await AgentLogRepo().log(
            AgentLogEntry(
                project_id=project_id,
                agent="PMAgent",
                action="batch_edit",
                details={"count": len(tickets)},
            )
        )
        return results
    finally:
        project.locked = False
        await project_repo.update(project)
