from ninja import Router, Schema, Path
from typing import List, Optional
from datetime import datetime
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from core.dataclasses.ticket_model import TicketModel
from core.datastore.repos.ticket_repo import TicketRepo
from core.dataclasses.project import Project
from core.datastore.repos.agent_log_repo import AgentLogRepo

router = Router(tags=["Tickets"])

class TicketIn(Schema):
    title: str
    description: Optional[str]
    due: Optional[datetime]
    eta: Optional[str]
    agents: Optional[str]     # comma-separated
    label: str
    severity: str             # ← new
    column: Optional[str]

class TicketOut(TicketIn):
    id: str
    created_at: datetime
    updated_at: datetime

# Guard helper
def ensure_not_locked(project_id: str):
    proj = get_object_or_404(Project, pk=project_id)
    if proj.locked:
        raise HttpError(409, "Project is in edit mode")

@router.get("/", response=List[TicketOut])
async def list_tickets(
    request,
    project_id: str = Path(..., description="Project ID from URL"),
):
    repo = TicketRepo()
    tickets = await repo.list_by_project(project_id)
    return tickets


@router.post("/", response=TicketOut)
async def create_ticket(request, project_id: str, data: TicketIn):
    ensure_not_locked(project_id)
    agent_list = data.agents.split(",") if data.agents else []
    model = TicketModel(
        project_id=project_id,
        title=data.title,
        description=data.description,
        due=data.due,
        eta=data.eta,
        agents=agent_list,
        label=data.label,
        severity=data.severity,
        column=data.column or "Backlog"
    )
    return await TicketRepo().create(model)

@router.patch("/{ticket_id}", response=TicketOut)
async def update_ticket(request, project_id: str, ticket_id: str, data: TicketIn):
    ensure_not_locked(project_id)
    updates = data.dict(exclude_unset=True)
    if "agents" in updates:
        updates["agents"] = updates["agents"].split(",")
    updated = await TicketRepo().update(ticket_id, updates)
    return updated

# Batch‐update with lock
@router.patch("/batch-update", response=List[TicketOut])
async def batch_update(request, project_id: str, tickets: List[TicketIn]):
    proj = get_object_or_404(Project, pk=project_id)
    # 1. Lock
    proj.locked = True
    proj.save(update_fields=["locked"])

    try:
        # 2. Determine deletions & upserts (similar to earlier example)
        repo = TicketRepo()
        existing_ids = set(await repo.list_ids_by_project(project_id))
        incoming_ids = {t.id for t in tickets if t.id}
        to_delete = existing_ids - incoming_ids
        if to_delete:
            await repo.delete_many(project_id, list(to_delete))

        results = []
        for t in tickets:
            data = t.dict(exclude_unset=True)
            # agents
            if "agents" in data:
                data["agents"] = data["agents"].split(",")
            if t.id:
                updated = await repo.update(t.id, data)
                results.append(updated)
            else:
                model = TicketModel(project_id=project_id, **data)
                created = await repo.create(model)
                results.append(created)

        # 3. Log
        await AgentLogRepo.log(
            project_id, agent="PMAgent", action="batch_edit",
            details={"count": len(tickets)}
        )

        return results
    finally:
        # 4. Unlock
        proj.locked = False
        proj.save(update_fields=["locked"])
