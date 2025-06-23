from asgiref.sync import sync_to_async
from ninja import Router, Path
from typing import List
from datetime import datetime
from django.shortcuts import get_object_or_404
from core.dataclasses.project import Project

from ninja import Schema

from core.datastore.repos.agent_log_repo import AgentLogRepo

router = Router(tags=["Activity"])

class LogOut(Schema):
    timestamp: datetime
    agent: str
    action: str
    details: dict

@router.get("/{project_id}/ticket-activity", response=List[LogOut])
async def ticket_activity(
    request,
    project_id: str = Path(..., description="Project ID"),
):
    # Validate project exists
    await sync_to_async(get_object_or_404)(Project, pk=project_id)

    repo = AgentLogRepo()
    logs = await repo.list_by_project(project_id, limit=100)
    # Map Mongo docs to LogOut
    return [
        LogOut(
          timestamp=log['timestamp'],
          agent=log['agent'],
          action=log['action'],
          details=log.get('details', {})
        )
        for log in logs
    ]
