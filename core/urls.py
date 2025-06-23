from django.contrib import admin
from django.urls import path


from core.api import api

from core.endpoints.ui.ui_base import index
from core.sse.chat_stream_handler import sse_chat_stream

urlpatterns = [
    path('admin/', admin.site.urls),
    path("", index, name="home"),
    path("chat/stream/", sse_chat_stream),
    path("api/", api.urls),
]
