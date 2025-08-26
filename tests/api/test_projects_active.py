import os
import sys
import pathlib
import django
from django.test import Client, TestCase
from unittest.mock import AsyncMock, patch
from django.conf import settings

# Ensure project root on path for imports
sys.path.append(str(pathlib.Path(__file__).resolve().parents[2]))
from core.dataclasses.project import Project

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "athba.settings")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("DEBUG", "1")
os.environ.setdefault("MONGO_USER", "test")
os.environ.setdefault("MONGO_PASS", "test")
django.setup()


class ActiveProjectEndpointTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("core.endpoints.projects.ps.get_project_by_id", new_callable=AsyncMock)
    def test_with_session(self, mock_get):
        mock_get.return_value = Project(_id="123", name="Test Project")
        session = self.client.session
        session["project_id"] = "123"
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        response = self.client.get("/api/projects/active/")
        assert response.status_code == 200
        assert response.json() == {"id": "123", "name": "Test Project"}

    def test_without_session(self):
        response = self.client.get("/api/projects/active/")
        assert response.status_code == 200
        assert response.json() == {"id": None, "name": None}

    @patch("core.endpoints.projects.ps.get_project_by_id", new_callable=AsyncMock)
    def test_stale_id(self, mock_get):
        mock_get.return_value = None
        session = self.client.session
        session["project_id"] = "999"
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        response = self.client.get("/api/projects/active/")
        assert response.status_code == 200
        assert response.json() == {"id": "999", "name": None}
