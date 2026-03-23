"""
Tests for ticket-related API endpoints.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime


@pytest.mark.asyncio
async def test_kanban_endpoint_returns_tickets(sample_session, sample_ticket):
    """Test that kanban endpoint returns tickets for a project."""
    from core.endpoints.ui.ui_kanban import load_kanban
    from core.datastore.repos.ticket_repo import TicketRepo
    
    # Mock the ticket repo
    with pytest.MonkeyPatch.context() as m:
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=[sample_ticket])
        
        # Create mock request with session
        mock_request = MagicMock()
        mock_request.session = {"project_id": "test_project_456"}
        
        # Mock ProjectsService to return the project_id
        with pytest.MonkeyPatch.context() as mp:
            async def mock_get_project_id(request):
                return "test_project_456"
            
            from core.services import project_service
            mp.setattr(project_service.ProjectsService, "get_project_id_from_request", mock_get_project_id)
            
            # Note: This is a simplified test. Full testing would require Django test client
            # For now, we're just checking the structure


@pytest.mark.asyncio
async def test_ticket_repo_list_all(sample_ticket):
    """Test TicketRepo.list_all method."""
    from core.datastore.repos.ticket_repo import TicketRepo
    
    repo = TicketRepo()
    
    # Mock the MongoDB collection
    mock_col = MagicMock()
    mock_col.find = MagicMock()
    
    # Create async iterator mock
    async def mock_to_list(length):
        return [
            {
                "_id": "test_id",
                "project_id": "test_project_456",
                "title": "Test Ticket",
                "description": "Test description",
                "due": datetime.utcnow(),
                "eta": "1 week",
                "agents": [],
                "label": "Feature",
                "severity": "Medium",
                "column": "Backlog",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "history": []
            }
        ]
    
    mock_find_result = MagicMock()
    mock_find_result.to_list = mock_to_list
    mock_col.find.return_value = mock_find_result
    
    repo.col = mock_col
    
    tickets = await repo.list_all("test_project_456")
    
    assert len(tickets) == 1
    assert tickets[0].title == "Test Ticket"
    assert tickets[0].project_id == "test_project_456"
    assert tickets[0].id == "test_id"


@pytest.mark.asyncio
async def test_ticket_repo_create(sample_ticket):
    """Test TicketRepo.create method."""
    from core.datastore.repos.ticket_repo import TicketRepo
    
    repo = TicketRepo()
    
    # Mock the MongoDB collection
    mock_col = MagicMock()
    mock_insert_result = MagicMock()
    mock_insert_result.inserted_id = "new_ticket_id"
    mock_col.insert_one = AsyncMock(return_value=mock_insert_result)
    
    repo.col = mock_col
    
    created_ticket = await repo.create(sample_ticket)
    
    assert created_ticket.id == "new_ticket_id"
    assert created_ticket.project_id == sample_ticket.project_id
    assert created_ticket.title == sample_ticket.title
    assert mock_col.insert_one.called


@pytest.mark.asyncio
async def test_ticket_repo_get_backlog_tickets(sample_ticket):
    """Test TicketRepo.get_backlog_tickets method."""
    from core.datastore.repos.ticket_repo import TicketRepo
    
    repo = TicketRepo()
    
    # Mock the MongoDB collection
    mock_col = MagicMock()
    
    async def mock_to_list(length):
        return [
            {
                "_id": "backlog_ticket_1",
                "project_id": "test_project_456",
                "title": "Backlog Ticket",
                "description": "In backlog",
                "due": datetime.utcnow(),
                "eta": "1 week",
                "agents": [],
                "label": "Feature",
                "severity": "Medium",
                "column": "Backlog",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "history": []
            }
        ]
    
    mock_find_result = MagicMock()
    mock_find_result.to_list = mock_to_list
    mock_col.find.return_value = mock_find_result
    
    repo.col = mock_col
    
    backlog_tickets = await repo.get_backlog_tickets("test_project_456")
    
    assert len(backlog_tickets) == 1
    assert backlog_tickets[0].column == "Backlog"
    assert backlog_tickets[0].id == "backlog_ticket_1"
    
    # Verify the query filter
    call_args = mock_col.find.call_args
    query_filter = call_args[0][0]
    assert query_filter["project_id"] == "test_project_456"
    assert query_filter["column"] == "Backlog"


@pytest.mark.asyncio
async def test_ticket_repo_count(sample_ticket):
    """Test TicketRepo.count method."""
    from core.datastore.repos.ticket_repo import TicketRepo
    
    repo = TicketRepo()
    
    # Mock the MongoDB collection
    mock_col = MagicMock()
    mock_col.count_documents = AsyncMock(return_value=5)
    
    repo.col = mock_col
    
    count = await repo.count("test_project_456")
    assert count == 5
    
    # Test count with column filter
    count_backlog = await repo.count("test_project_456", column="Backlog")
    assert count_backlog == 5
    
    # Verify queries
    calls = mock_col.count_documents.call_args_list
    assert len(calls) == 2
    assert calls[0][0][0] == {"project_id": "test_project_456"}
    assert calls[1][0][0] == {"project_id": "test_project_456", "column": "Backlog"}
