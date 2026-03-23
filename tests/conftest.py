# Test fixtures for agents and behaviors
import pytest
from datetime import datetime
from core.dataclasses.projses import Projses
from core.dataclasses.project import Project
from core.dataclasses.ticket_model import TicketModel
from core.dataclasses.history_entry import HistoryEntry


@pytest.fixture
def sample_session():
    """Create a sample session for testing."""
    return Projses(
        session_id="test_session_123",
        project_id="test_project_456",
        agent_name="Architect"
    )


@pytest.fixture
def sample_project():
    """Create a sample project for testing."""
    return Project(
        id="test_project_456",
        name="Test Project",
        description="A test project",
        active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )


@pytest.fixture
def sample_spec_content():
    """Create sample specification content."""
    return {
        "sections": [
            {
                "name": "overview",
                "body": "# Project Overview\n\nBuild a web application for managing customer orders.\n\n## Features\n- User authentication\n- Order management\n- Payment processing"
            },
            {
                "name": "requirements",
                "body": "# Requirements\n\n1. Users must be able to register and login\n2. Users can create, view, and cancel orders\n3. Integrate with Stripe for payments"
            }
        ],
        "meta": {"version": 1}
    }


@pytest.fixture
def sample_spec_document(sample_spec_content):
    """Create a sample spec document as it would be stored in MongoDB."""
    return {
        "project_id": "test_project_456",
        "version": 1,
        "content": sample_spec_content,
        "author": "human",
        "created_at": datetime.utcnow(),
        "approved": True,
        "approved_by": "human",
        "approved_at": datetime.utcnow()
    }


@pytest.fixture
def sample_ticket():
    """Create a sample ticket for testing."""
    return TicketModel(
        project_id="test_project_456",
        title="Implement user authentication",
        description="Create login and registration functionality with JWT tokens",
        due=datetime.utcnow(),
        eta="1 week",
        agents=[],
        label="Feature",
        severity="High",
        column="Backlog",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        history=[
            HistoryEntry(
                timestamp=datetime.utcnow(),
                event="created",
                actor="Architect",
                details="Ticket generated from specification analysis"
            )
        ],
        id="test_ticket_789"
    )


@pytest.fixture
def sample_tickets():
    """Create a list of sample tickets."""
    return [
        {
            "title": "Implement user authentication system",
            "description": "Create login/logout functionality with JWT tokens. Users can register, login, logout, and maintain session state.",
            "severity": "High",
            "label": "Feature",
            "eta": "1 week",
            "estimated_days": 7
        },
        {
            "title": "Build order management interface",
            "description": "Allow users to create, view, edit, and cancel orders. Display order history and status.",
            "severity": "High",
            "label": "Feature",
            "eta": "2 weeks",
            "estimated_days": 14
        },
        {
            "title": "Integrate Stripe payment processing",
            "description": "Set up Stripe integration for handling payments. Include webhook handlers for payment events.",
            "severity": "Medium",
            "label": "Feature",
            "eta": "1 week",
            "estimated_days": 7
        }
    ]
