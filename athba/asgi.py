import os
from pathlib import Path
from dotenv import load_dotenv

from django.core.asgi import get_asgi_application
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.staticfiles import StaticFiles

from core.sse.chat_stream_handler import sse_chat_stream

# 1. Load environment
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# 2. Configure Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "commercial_agentic_ai.settings")
import django
django.setup()

# 3. Get Django's ASGI app
django_asgi_app = get_asgi_application()

sse_routes = [
    Route("/chat/stream/", sse_chat_stream),
]

# 4. Create Starlette app to serve static + mount Django
app = Starlette(routes=sse_routes, debug=os.getenv("DEBUG", "False") == "True")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static", html=False), name="static")
app.mount("/", django_asgi_app)


# 5. Final ASGI application
application = app



