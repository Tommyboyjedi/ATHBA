from unittest.mock import MagicMock

import pytest

from core.agents.spec_agent import SpecBuilderAgent
from core.dataclasses.history_entry import HistoryEntry
from core.dataclasses.projses import Projses
from core.dataclasses.ticket_model import TicketModel
from core.datastore.repos import ticket_repo as ticket_repo_module
from core.datastore.repos.conversation_repo import ConversationRepo
from core.datastore.repos.project_repo import ProjectRepo
from core.datastore.repos.spec_version_repo import SpecVersionRepo
from core.datastore.repos.ticket_repo import TicketRepo


def test_history_entry_maps_legacy_fields():
    entry = HistoryEntry(timestamp="now", agent="Architect", action="created", details="x")

    assert entry.actor == "Architect"
    assert entry.event == "created"


def test_ticket_model_supports_minimal_construction():
    ticket = TicketModel(project_id="p1", title="Implement flow")

    assert ticket.description == ""
    assert ticket.column == "Backlog"
    assert ticket.id == ""
    assert ticket.history == []


def test_ticket_repo_init_is_lazy(monkeypatch):
    def explode():
        raise AssertionError("get_mongo_db should not run during repo construction")

    monkeypatch.setattr(ticket_repo_module, "get_mongo_db", explode)

    repo = TicketRepo()

    assert repo._col is None


@pytest.mark.asyncio
async def test_spec_version_proxy_normalizes_raw_collection():
    class FakeCol:
        async def find_one(self, *args, **kwargs):
            return {
                "content": {"sections": [{"name": "raw", "body": "hello"}]},
            }

    proxy = SpecVersionRepo(collection=FakeCol()).col
    doc = await proxy.find_one({})

    assert doc["content"] == "hello"


def test_spec_builder_agent_exposes_spec_repo():
    agent = SpecBuilderAgent(Projses(session_id="s1", project_id="p1", agent_name="Spec"))

    assert isinstance(agent.spec_repo, SpecVersionRepo)


def test_other_repos_init_lazily():
    project_repo = ProjectRepo(db=MagicMock())
    conversation_repo = ConversationRepo(collection=MagicMock())

    assert project_repo._collection is None
    assert conversation_repo._col is not None
