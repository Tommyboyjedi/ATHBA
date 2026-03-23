"""
Integration tests for the spec-to-tickets workflow.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.agents.spec_agent import SpecBuilderAgent
from core.agents.architect_agent import ArchitectAgent
from core.agents.behaviors.spec.finalize_spec_behavior import FinalizeSpecBehavior
from core.dataclasses.llm_intent import LlmIntent
import asyncio


@pytest.mark.asyncio
async def test_spec_finalization_triggers_architect(sample_session, sample_spec_document):
    """Test that finalizing a spec triggers the Architect agent."""
    # Create spec agent and finalize behavior
    spec_agent = SpecBuilderAgent(sample_session)
    finalize_behavior = FinalizeSpecBehavior()
    
    # Mock the spec repo
    spec_agent.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    spec_agent.spec_repo.update = AsyncMock()
    
    # Mock the architect agent initialization and execution
    with patch('core.agents.behaviors.spec.finalize_spec_behavior.ArchitectAgent') as MockArchitect:
        mock_architect_instance = MagicMock()
        mock_architect_instance.initialize = AsyncMock()
        mock_architect_instance.run = AsyncMock(return_value=[
            MagicMock(content="Tickets created", sender="Architect")
        ])
        MockArchitect.return_value = mock_architect_instance
        
        # Create intent to finalize spec
        intent = LlmIntent(
            response="Finalizing spec",
            intent="finalize_spec",
            agents_routing=[],
            entities={}
        )
        
        # Run the finalize behavior
        result = await finalize_behavior.run(spec_agent, "finalize the spec", intent)
        
        assert result is not None
        assert len(result) > 0
        assert "finalized and approved" in result[0].content
        
        # Give async task time to run
        await asyncio.sleep(0.1)
        
        # Verify architect was called
        MockArchitect.assert_called_once()


@pytest.mark.asyncio
async def test_full_workflow_spec_to_tickets(sample_session, sample_spec_document, sample_tickets):
    """Test the complete workflow from spec finalization to ticket creation."""
    import json
    
    # Step 1: Finalize the spec
    spec_agent = SpecBuilderAgent(sample_session)
    finalize_behavior = FinalizeSpecBehavior()
    
    spec_agent.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    spec_agent.spec_repo.update = AsyncMock()
    
    intent = LlmIntent(response="", intent="finalize_spec", agents_routing=[], entities={})
    
    # Mock the entire architect execution
    created_tickets = []
    
    async def mock_architect_run(user_input):
        # Simulate ticket creation
        from core.dataclasses.chat_message import ChatMessage
        return [ChatMessage(sender="Architect", content=f"Created {len(sample_tickets)} tickets")]
    
    with patch('core.agents.behaviors.spec.finalize_spec_behavior.ArchitectAgent') as MockArchitect:
        mock_architect = MagicMock()
        mock_architect.initialize = AsyncMock()
        mock_architect.run = mock_architect_run
        MockArchitect.return_value = mock_architect
        
        # Finalize spec
        finalize_result = await finalize_behavior.run(spec_agent, "finalize spec", intent)
        
        assert finalize_result is not None
        assert "approved" in finalize_result[0].content
        
        # Wait for async task
        await asyncio.sleep(0.2)
        
        # Verify workflow completed
        assert mock_architect.initialize.called
        assert mock_architect.run.called


@pytest.mark.asyncio
async def test_architect_creates_tickets_with_correct_metadata(sample_session, sample_spec_document):
    """Test that tickets created by Architect have correct metadata."""
    architect = ArchitectAgent(sample_session)
    architect.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    
    created_tickets = []
    
    async def mock_create(ticket):
        ticket.id = f"ticket_{len(created_tickets)}"
        created_tickets.append(ticket)
        return ticket
    
    architect.ticket_repo.create = mock_create
    
    # Mock Anthropic provider to return tickets
    import json
    with patch('core.agents.helpers.llm_exchange.AnthropicProvider') as MockProvider:
        mock_provider_instance = MagicMock()
        from core.llm.contracts.provider import NormalizedResult
        
        # Mock both calls: get_intent and get_response
        mock_provider_instance.invoke.side_effect = [
            # First call for get_intent
            NormalizedResult(
                text='[{"response": "Analyzing", "intent": "analyze_spec", "agents_routing": [], "entities": {}}]',
                usage={"input_tokens": 100, "output_tokens": 50},
                raw={}
            ),
            # Second call for get_response (ticket generation)
            NormalizedResult(
                text=json.dumps([
                    {
                        "title": "Setup authentication",
                        "description": "Implement JWT auth",
                        "severity": "High",
                        "label": "Feature",
                        "eta": "1 week",
                        "estimated_days": 7
                    }
                ]),
                usage={"input_tokens": 500, "output_tokens": 200},
                raw={}
            )
        ]
        MockProvider.return_value = mock_provider_instance
        
        await architect.run("analyze spec")
        
        # Verify tickets have correct metadata
        assert len(created_tickets) == 1
        ticket = created_tickets[0]
        
        assert ticket.project_id == sample_session.project_id
        assert ticket.column == "Backlog"
        assert ticket.agents == []
        assert ticket.title == "Setup authentication"
        assert ticket.severity == "High"
        assert ticket.label == "Feature"
        assert len(ticket.history) > 0
        assert ticket.history[0].actor == "Architect"
        assert ticket.history[0].event == "created"


@pytest.mark.asyncio
async def test_spec_approval_metadata_saved(sample_session, sample_spec_document):
    """Test that spec approval metadata is correctly saved."""
    spec_agent = SpecBuilderAgent(sample_session)
    finalize_behavior = FinalizeSpecBehavior()
    
    spec_agent.spec_repo.find = AsyncMock(return_value=[sample_spec_document])
    
    update_calls = []
    
    async def mock_update(filter_dict, update_dict, **kwargs):
        update_calls.append((filter_dict, update_dict))
    
    spec_agent.spec_repo.update = mock_update
    
    # Mock architect to prevent actual execution
    with patch('core.agents.behaviors.spec.finalize_spec_behavior.ArchitectAgent'):
        intent = LlmIntent(response="", intent="finalize_spec", agents_routing=[], entities={})
        await finalize_behavior.run(spec_agent, "finalize", intent)
        
        # Check that update was called with approval metadata
        assert len(update_calls) == 1
        filter_dict, update_dict = update_calls[0]
        
        assert filter_dict["project_id"] == sample_session.project_id
        assert filter_dict["version"] == 1
        assert update_dict["approved"] is True
        assert update_dict["approved_by"] == "human"
        assert "approved_at" in update_dict
