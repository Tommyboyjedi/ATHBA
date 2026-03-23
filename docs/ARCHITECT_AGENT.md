# Architect Agent Documentation

## Overview

The Architect Agent is responsible for analyzing approved project specifications and breaking them down into actionable development tickets. It serves as the bridge between high-level requirements (captured in specifications) and concrete development tasks.

## Responsibilities

1. **Specification Analysis**: Parse and understand approved project specifications
2. **Ticket Generation**: Create discrete, implementable development tickets
3. **Task Prioritization**: Assign severity levels and organize tickets by dependencies
4. **TDD Preparation**: Ensure each ticket has clear acceptance criteria for test-driven development

## Workflow

### 1. Automatic Triggering

The Architect agent is automatically triggered when a specification is finalized:

```
User: "finalize the spec"
  ↓
Spec Agent: Marks spec as approved in MongoDB
  ↓
Spec Agent: Triggers Architect agent asynchronously
  ↓
Architect: Analyzes spec and generates tickets
  ↓
Tickets: Saved to MongoDB in "Backlog" column
```

### 2. Manual Invocation

The Architect can also be invoked manually:

```
User: "analyze the specification"
  ↓
Architect: Retrieves latest approved spec
  ↓
Architect: Generates tickets
```

## Behaviors

### AnalyzeSpecBehavior

**Intent**: `analyze_spec`

**Process**:
1. Retrieves the latest specification version from MongoDB
2. Extracts specification text from sections
3. Sends spec to LLM with ticket generation prompt
4. Parses LLM response to extract ticket data
5. Validates and creates tickets in MongoDB
6. Returns summary of created tickets

**Fallback Mechanism**: If LLM parsing fails, creates 3 default tickets:
- Initial project setup
- Implement core features
- Add tests for core functionality

**Code Example**:
```python
{
  "title": "Implement user authentication system",
  "description": "Create login/logout functionality with JWT tokens...",
  "severity": "High",
  "label": "Feature",
  "eta": "1 week",
  "estimated_days": 7
}
```

### RefineTicketsBehavior

**Intent**: `refine_tickets`

**Status**: Stub implementation (planned for future enhancement)

**Planned Features**:
- Allow human to request ticket modifications
- Re-analyze portions of the specification
- Split or merge tickets based on feedback

### BasicReplyBehavior

**Intent**: `basic_reply`

**Purpose**: Handle general conversation and questions about the Architect's role.

## Ticket Structure

Each generated ticket includes:

```python
TicketModel(
    project_id: str              # Associated project
    title: str                   # Clear, actionable title (max 80 chars)
    description: str             # Detailed description with acceptance criteria
    severity: str                # Critical, High, Medium, Low
    label: str                   # Feature, Bug, Enhancement, Documentation, Testing
    eta: str                     # Human-readable estimate (e.g., "1 week")
    estimated_days: int          # Numeric estimate for sorting
    column: str                  # Always "Backlog" initially
    agents: List[str]            # Empty initially, assigned by Resource Director
    history: List[HistoryEntry]  # Audit trail of changes
    due: datetime                # Calculated from estimated_days
    created_at: datetime
    updated_at: datetime
)
```

## LLM Prompting Strategy

The Architect uses a structured prompt to ensure consistent ticket generation:

```
Analyze this project specification and break it down into development tickets.

Specification:
{spec_text}

For each distinct feature or requirement, create a ticket with:
- title: Clear, actionable title (max 80 chars)
- description: Detailed description including acceptance criteria
- severity: Critical, High, Medium, or Low
- label: Feature, Bug, Enhancement, Documentation, or Testing
- eta: Estimated time (e.g., "2 days", "1 week")
- estimated_days: Numeric estimate in days

Generate 3-8 tickets that cover the main features.
```

## Integration Points

### Spec Finalization

The `FinalizeSpecBehavior` in the Spec agent:
1. Marks the spec as approved in MongoDB
2. Spawns an async task to run the Architect agent
3. Streams Architect responses back to the chat

```python
# finalize_spec_behavior.py
asyncio.create_task(self._run_architect(agent.session))
```

### Kanban Board

Tickets created by the Architect are immediately visible on the Kanban board:
- Displayed in the "Backlog" column
- Can be manually edited using the Kanban edit mode
- Ready for assignment to Dev/Test pairs

### Agent Generator

The Architect is registered in the agent generator for routing:

```python
# agent_generator.py
if session.agent_name == "Architect":
    from core.agents.architect_agent import ArchitectAgent
    return ArchitectAgent(session)
```

## Testing

Comprehensive test coverage includes:

### Unit Tests
- `tests/agents/test_architect_agent.py` - Agent initialization and behavior loading
- `tests/behaviors/test_analyze_spec_behavior.py` - Ticket generation logic

### Integration Tests
- `tests/integration/test_spec_to_tickets_flow.py` - Full workflow from spec to tickets

### API Tests
- `tests/api/test_tickets.py` - Ticket repository operations

Total: 25 test cases covering:
- Agent initialization
- Behavior execution
- LLM response parsing
- Fallback mechanisms
- MongoDB operations
- Workflow integration

## Configuration

The Architect agent uses the model registry for LLM selection:

```python
# Uses agent_type = EAgent.Architect
# Default tier: ETier.STANDARD
# Can be escalated to ETier.HEAVY for complex specs
```

## Future Enhancements

1. **Dependency Detection**: Automatically identify ticket dependencies
2. **Story Point Estimation**: Use historical data for better estimates
3. **Template Support**: Pre-defined ticket templates for common features
4. **Multi-pass Analysis**: Iterative refinement of ticket breakdown
5. **Requirements Tracing**: Link tickets back to specific spec sections
6. **Epic Creation**: Group related tickets into epics

## Example Usage

### Typical Flow

```
1. User creates and builds specification with Spec agent
2. User: "finalize the spec"
3. Spec agent: "✅ Specification v1 finalized and approved!"
4. Architect (automatic): "Analyzing specification..."
5. Architect: "✅ Created 5 tickets:
   • Implement user authentication [High] - Feature
   • Build order management interface [High] - Feature
   • Integrate Stripe payments [Medium] - Feature
   • Add user profile management [Medium] - Feature
   • Write comprehensive tests [Medium] - Testing"
6. User: Views tickets on Kanban board
7. Resource Director: Assigns tickets to Dev/Test pairs
```

### Manual Refinement

```
User: "Can you refine the authentication ticket?"
Architect: "✅ I found 5 existing tickets. Ticket refinement is coming soon..."
```

## Error Handling

The Architect includes robust error handling:

1. **No Spec Found**: Returns helpful error message
2. **LLM Parsing Failure**: Uses fallback ticket generation
3. **Invalid Ticket Data**: Validates and fills in defaults
4. **Network Errors**: Gracefully degrades with informative messages

## Monitoring

Architect activity can be monitored through:

- Chat stream (real-time SSE updates)
- Ticket creation history in MongoDB
- Agent activity logs
- Kanban board state changes

## Summary

The Architect Agent is a critical component of the ATHBA system, transforming human-readable specifications into structured development tasks. It leverages LLM capabilities for intelligent ticket generation while maintaining fallback mechanisms for reliability.
