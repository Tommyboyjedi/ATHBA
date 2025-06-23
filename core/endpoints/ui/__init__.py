from ninja import Router
from .ui_code import router as code_router
from .ui_dashboard import router as dashboard_router
from .ui_spec import router as spec_router
from .ui_kanban import router as kanban_router
from .ui_overview import router as overview_router
from .ui_nav import router as nav_router


router = Router()
router.add_router("/code", code_router)
router.add_router("/dashboard", dashboard_router)
router.add_router("/spec", spec_router)
router.add_router("/kanban", kanban_router)
router.add_router("/overview", overview_router)
router.add_router("/nav", nav_router)

