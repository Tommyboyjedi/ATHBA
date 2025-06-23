# core/api.py
from ninja import NinjaAPI

from core.endpoints.chat import chat_router
from core.endpoints.projects import router as projects_router
from core.endpoints.snippets import router as snippets_router
from core.endpoints.tickets import router as tickets_router
from core.endpoints.config import router as config_router
from core.endpoints.activity import router as activity_router
from core.endpoints.dashboard import router as dashboard_router
from core.endpoints.spec import router as spec_router
from core.endpoints.ui import router as ui_router


# Single NinjaAPI instance
api = NinjaAPI(version='1.0.1', urls_namespace='projects_api')
# Register routers
api.add_router("/projects", projects_router)
api.add_router("/projects/{project_id}/tickets", tickets_router)
api.add_router("/projects/{project_id}/snippets", snippets_router)
api.add_router("/chat", chat_router)
api.add_router("/config", config_router)
api.add_router("/projects", activity_router)  # will pick up /{project_id}/ticket-activity/
api.add_router("/projects", dashboard_router)
api.add_router("/spec", spec_router)
api.add_router("/ui", ui_router)
# No URL patterns here; mount in core/urls.py
