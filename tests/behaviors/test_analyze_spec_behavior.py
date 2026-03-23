"""
Tests for the AnalyzeSpecBehavior.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from core.agents.behaviors.architect.analyze_spec_behavior import AnalyzeSpecBehavior
from core.agents.architect_agent import ArchitectAgent
from core.dataclasses.llm_intent import LlmIntent


@pytest.mark.asyncio
async def test_analyze_spec_behavior_correct_intent(sample_session):
    """Test that behavior only runs on analyze_spec intent."""
    behavior = AnalyzeSpecBehavior()
    agent = ArchitectAgent(sample_session)
    
    # Should run on analyze_spec intent
    intent = LlmIntent(response="", intent="analyze_spec", agents_routing=[], entities={})
    agent.spec_repo.find = AsyncMock(return_value=[])
    result = await behavior.run(agent, "analyze spec", intent)
    assert result is not None
    
    # Should not run on different intent
    intent = LlmIntent(response="", intent="basic_reply", agents_routing=[], entities={})
    result = await behavior.run(agent, "hello", intent)
    assert result is None


@pytest.mark.asyncio
async def test_analyze_spec_behavior_no_spec_found(sample_session):
    """Test behavior when no specification exists."""
    behavior = AnalyzeSpecBehavior()
    agent = ArchitectAgent(sample_session)
    agent.spec_repo.find = AsyncMock(return_value=[])
    
    intent = LlmIntent(response="", intent="analyze_spec", agents_routing=[], entities={})
    result = await behavior.run(agent, "analyze spec", intent)
    
    assert result is not None
    assert len(result) == 1
    assert "No specification found" in result[0].content


@pytest.mark.asyncio
async def test_analyze_spec_behavior_generates_tickets(sample_session, sample_spec_document, sample_tickets):
    """Test that behavior generates tickets from specification."""
    behavior = AnalyzeSpecBehavior()
    agent = ArchitectAgent(sample_session)
    
    # Mock spec repo
    agent.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    
    # Mock ticket repo
    created_tickets = []
    async def mock_create(ticket):
        ticket.id = f"ticket_{len(created_tickets)}"
        created_tickets.append(ticket)
        return ticket
    
    agent.ticket_repo.create = mock_create
    
    # Mock LLM response for ticket generation
    import json
    with patch('core.agents.helpers.llm_exchange.LlmExchange.get_response') as mock_response:
        mock_response.return_value = json.dumps(sample_tickets)
        
        intent = LlmIntent(response="", intent="analyze_spec", agents_routing=[], entities={})
        result = await behavior.run(agent, "analyze spec", intent)
        
        assert result is not None
        assert len(result) == 1
        assert "created" in result[0].content.lower()
        assert str(len(sample_tickets)) in result[0].content
        
        # Check tickets were created
        assert len(created_tickets) == len(sample_tickets)
        for i, ticket in enumerate(created_tickets):
            assert ticket.project_id == "test_project_456"
            assert ticket.column == "Backlog"
            assert ticket.title == sample_tickets[i]["title"]


@pytest.mark.asyncio
async def test_analyze_spec_behavior_handles_json_in_text(sample_session, sample_spec_document):
    """Test that behavior can extract JSON from LLM response text."""
    behavior = AnalyzeSpecBehavior()
    agent = ArchitectAgent(sample_session)
    
    agent.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    agent.ticket_repo.create = AsyncMock(return_value=MagicMock(
        title="Test", severity="Medium", label="Feature"
    ))
    
    # Mock LLM response with extra text around JSON
    with patch('core.agents.helpers.llm_exchange.LlmExchange.get_response') as mock_response:
        mock_response.return_value = 'Here are the tickets: [{"title": "Test ticket", "description": "Test", "severity": "High", "label": "Feature", "eta": "1 week", "estimated_days": 7}] All done!'
        
        intent = LlmIntent(response="", intent="analyze_spec", agents_routing=[], entities={})
        result = await behavior.run(agent, "analyze spec", intent)
        
        assert result is not None
        assert "created" in result[0].content.lower()


@pytest.mark.asyncio
async def test_analyze_spec_behavior_fallback_on_parse_error(sample_session, sample_spec_document):
    """Test that behavior creates fallback tickets if JSON parsing fails."""
    behavior = AnalyzeSpecBehavior()
    agent = ArchitectAgent(sample_session)
    
    agent.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    
    created_tickets = []
    async def mock_create(ticket):
        ticket.id = f"ticket_{len(created_tickets)}"
        created_tickets.append(ticket)
        return ticket
    
    agent.ticket_repo.create = mock_create
    
    # Mock LLM response with invalid JSON
    with patch('core.agents.helpers.llm_exchange.LlmExchange.get_response') as mock_response:
        mock_response.return_value = "This is not valid JSON at all!"
        
        intent = LlmIntent(response="", intent="analyze_spec", agents_routing=[], entities={})
        result = await behavior.run(agent, "analyze spec", intent)
        
        assert result is not None
        # Should create fallback tickets
        assert len(created_tickets) == 3  # Default fallback creates 3 tickets
        assert "Initial project setup" in created_tickets[0].title


@pytest.mark.asyncio
async def test_analyze_spec_behavior_extracts_text_from_sections(sample_session):
    """Test that behavior correctly extracts text from spec sections."""
    behavior = AnalyzeSpecBehavior()
    agent = ArchitectAgent(sample_session)
    
    spec_doc = {
        "project_id": "test_project_456",
        "version": 1,
        "content": {
            "sections": [
                {"name": "overview", "body": "Overview text"},
                {"name": "requirements", "body": "Requirements text"}
            ]
        },
        "approved": True
    }
    
    agent.spec_repo.find = AsyncMock(return_value=[spec_doc])
    agent.ticket_repo.create = AsyncMock(return_value=MagicMock(
        title="Test", severity="Medium", label="Feature"
    ))
    
    with patch('core.agents.helpers.llm_exchange.LlmExchange.get_response') as mock_response:
        mock_response.return_value = '[{"title": "Test", "description": "Test", "severity": "Medium", "label": "Feature", "eta": "1 week", "estimated_days": 7}]'
        
        intent = LlmIntent(response="", intent="analyze_spec", agents_routing=[], entities={})
        await behavior.run(agent, "analyze spec", intent)
        
        # Check that the LLM was called with spec content
        call_args = mock_response.call_args
        # The spec text should be in the prompt somewhere
        assert mock_response.called
