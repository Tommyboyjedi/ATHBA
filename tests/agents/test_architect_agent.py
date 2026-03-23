"""
Tests for the Architect Agent.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.agents.architect_agent import ArchitectAgent
from core.dataclasses.llm_intent import LlmIntent


@pytest.mark.asyncio
async def test_architect_agent_initialization(sample_session):
    """Test that Architect agent initializes correctly."""
    agent = ArchitectAgent(sample_session)
    
    assert agent.name == "Architect"
    assert agent.session.project_id == "test_project_456"
    assert agent.session.agent_name == "Architect"
    assert agent.ticket_repo is not None
    assert agent.spec_repo is not None
    assert len(agent.behaviors) > 0


@pytest.mark.asyncio
async def test_architect_agent_report(sample_session, sample_project):
    """Test that Architect agent generates a status report."""
    agent = ArchitectAgent(sample_session)
    agent._project = sample_project
    
    report = await agent.report()
    
    assert report["agent"] == "Architect"
    assert report["status"] == "Active"
    assert report["project_id"] == "test_project_456"


@pytest.mark.asyncio
async def test_architect_agent_has_analyze_spec_behavior(sample_session):
    """Test that Architect agent has analyze_spec behavior loaded."""
    agent = ArchitectAgent(sample_session)
    
    behavior_names = [behavior.__class__.__name__ for behavior in agent.behaviors]
    assert "AnalyzeSpecBehavior" in behavior_names


@pytest.mark.asyncio
async def test_architect_agent_has_refine_tickets_behavior(sample_session):
    """Test that Architect agent has refine_tickets behavior loaded."""
    agent = ArchitectAgent(sample_session)
    
    behavior_names = [behavior.__class__.__name__ for behavior in agent.behaviors]
    assert "RefineTicketsBehavior" in behavior_names


@pytest.mark.asyncio
async def test_architect_agent_llm_prompt_includes_key_instructions(sample_session):
    """Test that Architect agent LLM prompt contains important instructions."""
    agent = ArchitectAgent(sample_session)
    
    prompt = agent.llm_prompt
    
    assert "Architect Agent" in prompt
    assert "analyze" in prompt.lower()
    assert "ticket" in prompt.lower()
    assert "specification" in prompt.lower()
    assert "analyze_spec" in prompt
    assert "refine_tickets" in prompt


@pytest.mark.asyncio
async def test_architect_agent_run_triggers_behaviors(sample_session):
    """Test that running the agent triggers appropriate behaviors."""
    agent = ArchitectAgent(sample_session)
    
    # Mock the LLM exchange to return analyze_spec intent
    # Note: Architect uses cloud provider, so we mock AnthropicProvider
    with patch('core.agents.helpers.llm_exchange.AnthropicProvider') as MockProvider:
        mock_provider_instance = MagicMock()
        
        # Mock the invoke method to return intent response
        from core.llm.contracts.provider import NormalizedResult
        mock_provider_instance.invoke.return_value = NormalizedResult(
            text='[{"response": "I\'ll analyze the specification", "intent": "analyze_spec", "agents_routing": [], "entities": {}}]',
            usage={"input_tokens": 100, "output_tokens": 50},
            raw={}
        )
        MockProvider.return_value = mock_provider_instance
        
        # Mock the spec repo to return a spec
        agent.spec_repo.find = AsyncMock(return_value=[
            {
                "project_id": "test_project_456",
                "version": 1,
                "content": {"sections": [{"name": "test", "body": "Test spec content"}]},
                "approved": True
            }
        ])
        
        # Mock the ticket repo
        agent.ticket_repo.create = AsyncMock(return_value=MagicMock(
            title="Test ticket",
            severity="Medium",
            label="Feature"
        ))
        
        # Mock second invoke for ticket generation
        mock_provider_instance.invoke.side_effect = [
            # First call for get_intent
            NormalizedResult(
                text='[{"response": "I\'ll analyze the specification", "intent": "analyze_spec", "agents_routing": [], "entities": {}}]',
                usage={"input_tokens": 100, "output_tokens": 50},
                raw={}
            ),
            # Second call for ticket generation in get_response
            NormalizedResult(
                text='[{"title": "Test ticket", "description": "Test", "severity": "Medium", "label": "Feature", "eta": "1 week", "estimated_days": 7}]',
                usage={"input_tokens": 200, "output_tokens": 100},
                raw={}
            )
        ]
        
        responses = await agent.run("analyze the specification")
        
        assert len(responses) > 0
        # Should return ChatMessage responses
        assert all(hasattr(r, 'content') for r in responses)
