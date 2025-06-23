from uuid import uuid4
from core.dataclasses.projses import Projses
from asgiref.sync import sync_to_async

from core.datastore.repos.project_repo import ProjectRepo


class SessionService:

    async def manage(self, request) -> Projses:
        request_session = request.session

        session_id = request.session.session_key
        if not session_id:
            await sync_to_async(request.session.save)()
            session_id = request.session.session_key

        project_id = await sync_to_async(request_session.get)("project_id")
        if not project_id or project_id == '0':
            all_projects = await ProjectRepo().list_all()
            active_projects = [p for p in all_projects if p.active]
            if len(active_projects) > 0:
                project_id = str(active_projects[0].id)
            else:
                project_id = "0"
            await sync_to_async(request_session.__setitem__)("project_id", project_id)

        agent_name = await sync_to_async(request_session.get)("agent_name")
        if agent_name is None:
            agent_name = "PM"
            await sync_to_async(request_session.__setitem__)("agent_name", agent_name)

        return Projses(session_id=session_id, project_id=project_id, agent_name=agent_name)

